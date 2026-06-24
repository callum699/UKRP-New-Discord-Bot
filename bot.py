import discord
from discord.ext import commands
from discord import app_commands

import aiosqlite
import time
import asyncio
import re
from datetime import timedelta, datetime, timezone
import zoneinfo

from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise ValueError("❌ DISCORD_TOKEN not found")

# ================== CONFIG ==================
OWNER_IDS = [738790396511125654, 371627538923126791]
GUILD_ID = 1457118167078801631

REQUEST_ROLE_IDS = [1460998934842441809, 1457118167204630725, 1457118167108161540]
GLOBALBAN_REQUEST_ROLE_IDS = [1460998934842441809, 1457118167204630725]
ADMIN_ROLE_IDS = [1457118167204630728]
LOA_TRACKER_ROLE_ID =  1457118167095841075
INACTIVITY_WARNING_ROLE_ID = 1457118167091642440
LOA_COOLDOWN_ROLE_ID = 1457118167108161545

# Police Blacklist / Removal commands
POLICE_COMMAND_ROLE_IDS = [
    1457118167204630725,   # Gold Command role ID
    1460998934842441809    # Professional Standards role ID
]

VERIFICATION_HEADER_ROLE_ID = 1461656344510730383   # ▬▬▬▬ VERIFICATION ROLES ▬▬▬▬ role ID
VERIFIED_ROLE_ID = 1457118167108161542              # Verified role ID

POLICE_BARRED_LIST_ROLE_ID = 1457118167091642449    # Police Barred List role ID
REMOVAL_COOLDOWN_ROLE_ID = 1457118167078801640      # Removal Cooldown role ID

# Cross-guild removal (Radio Traffic Server)
RADIO_TRAFFIC_GUILD_ID = 1457403990433206344        # ← Guild ID of the Radio Traffic server

# Roles to remove in the Radio Traffic server (use IDs)
CROSS_GUILD_ROLES_TO_REMOVE = [
    1457403990449852427,   # Police Personnel
    1497974641292214363,   # EOC Operator
    1509223811306881286,   # EOC Manager
    1457403990458499318,   # RTO Ranking Permissions
    1457403990458499319,   # ✰✰ Police Service High Command ✰✰
    1466005018393055253,   # Professional Standards
    1504096735402922065    # ✰✰✰ Police Service Gold Command ✰✰✰
]

# Training Command Roles & Channels
ENTRY_PROGRAMME_INSTRUCTOR_ROLE_ID = 1457118167095841079   # ← Fill this in
ROADS_INSTRUCTOR_ROLE_ID           = 1510303284299304961   # ← Fill this in
STUDENT_CONSTABLE_ROLE_ID          = 1457118167196504127   # ← Fill this in

TRAINING_ANNOUNCEMENTS_CHANNEL_ID  = 1457118170983956611   # ← Channel where the embed is posted

RESPONSE_TRAINING_VC_ID = 1457118171181093100

# Second cross-guild server (Main Server)
MAIN_SERVER_GUILD_ID = 1452412377034264576          # ← Guild ID of the "Main Server"

# Role to remove/restore in the Main Server
MAIN_SERVER_ROLE_TO_MANAGE = 1452412377101238346    # ← UK:RP | Service Head role ID

# Roles allowed to use /role command per guild
ROLE_COMMAND_ALLOWED_ROLES = {
    1452412377034264576: [          # Guild 1
        "UK:RP | Owner",
        "UK:RP | Co-Owner",
        "UK:RP | Community Manager",
        "UK:RP | Management Team",
        "UK:RP | Trial Management"
    ],
    1457403990433206344: [          # Guild 2
        "RTO Ranking Permissions"
    ],
    1457118167078801631: [          # Guild 3 (Main)
        "● Discord Ranking Permissions ●"
    ]
}

LOA_LOG_CHANNEL_ID = 1511706584189767700
LOG_CHANNEL_ID = 1504537214829461677

DB_NAME = "globalbans.db"

# ================== PERMISSION HELPERS ==================
def has_request_role(user):
    return any(role.id in REQUEST_ROLE_IDS for role in user.roles)

def is_admin(user):
    if user.id == OWNER_IDS:
        return True
    return any(role.id in ADMIN_ROLE_IDS for role in user.roles)

def can_manage_roles(user: discord.Member, guild: discord.Guild) -> bool:
    """Check if user can use /role command based on guild"""
    # Always allow Owners and Admins
    if is_admin(user):
        return True

    # Get the list of allowed role names for this guild
    allowed_role_names = ROLE_COMMAND_ALLOWED_ROLES.get(guild.id, [])

    # Check if the user has any of the allowed roles in this guild
    for role_name in allowed_role_names:
        role = discord.utils.get(guild.roles, name=role_name)
        if role and role in user.roles:
            return True

    return False

def can_use_police_commands(user: discord.Member) -> bool:
    """Check if user can use /policeblacklist and /policeremoval (ID-based)"""
    if is_admin(user):
        return True
    return any(role.id in POLICE_COMMAND_ROLE_IDS for role in user.roles)

async def save_role_backup(member: discord.Member, backup_type: str):
    """Save roles in main guild + Radio Traffic + Main Server"""
    guild = member.guild

    # Main guild
    role_ids = [str(r.id) for r in member.roles if r != guild.default_role]
    await _save_backup_to_db(str(member.id), str(guild.id), backup_type, ",".join(role_ids))

    # Radio Traffic server
    other_guild = bot.get_guild(RADIO_TRAFFIC_GUILD_ID)
    if other_guild:
        other_member = other_guild.get_member(member.id)
        if other_member:
            other_role_ids = [str(r.id) for r in other_member.roles if r != other_guild.default_role]
            await _save_backup_to_db(str(member.id), str(other_guild.id), backup_type, ",".join(other_role_ids))

    # Main Server (new)
    main_guild = bot.get_guild(MAIN_SERVER_GUILD_ID)
    if main_guild:
        main_member = main_guild.get_member(member.id)
        if main_member:
            main_role_ids = [str(r.id) for r in main_member.roles if r != main_guild.default_role]
            await _save_backup_to_db(str(member.id), str(main_guild.id), backup_type, ",".join(main_role_ids))

async def delete_role_backup(user_id: int, guild_id: int, backup_type: str):
    """Delete the role backup after successful restoration"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""DELETE FROM role_backups 
                            WHERE user_id = ? AND guild_id = ? AND backup_type = ?""",
                         (str(user_id), str(guild_id), backup_type))
        await db.commit()

async def _save_backup_to_db(user_id: str, guild_id: str, backup_type: str, roles_str: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""INSERT OR REPLACE INTO role_backups 
            (user_id, guild_id, backup_type, previous_roles, timestamp)
            VALUES (?, ?, ?, ?, ?)""",
            (user_id, guild_id, backup_type, roles_str, int(time.time())))
        await db.commit()


async def restore_from_backup(member: discord.Member, backup_type: str, special_role_id: int):
    """Remove special role and restore previous roles (Main Guild)"""
    guild = member.guild
    special_role = guild.get_role(special_role_id)
    bot_top_role = guild.me.top_role

    ver_header = guild.get_role(VERIFICATION_HEADER_ROLE_ID)
    verified = guild.get_role(VERIFIED_ROLE_ID)

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            """SELECT previous_roles FROM role_backups 
               WHERE user_id = ? AND guild_id = ? AND backup_type = ?""",
            (str(member.id), str(guild.id), backup_type)
        ) as cursor:
            row = await cursor.fetchone()

    # Remove special role
    if special_role and special_role in member.roles:
        await member.remove_roles(special_role, reason=f"Removed {backup_type}")

    roles_added = []

    if row and row[0]:
        previous_role_ids = [int(rid) for rid in row[0].split(",") if rid.strip()]

        for rid in previous_role_ids:
            role = guild.get_role(rid)
            if role and role != special_role:
                if role.position < bot_top_role.position:
                    roles_added.append(role)

    # Always ensure verification roles
    if ver_header and ver_header not in roles_added and ver_header.position < bot_top_role.position:
        roles_added.append(ver_header)
    if verified and verified not in roles_added and verified.position < bot_top_role.position:
        roles_added.append(verified)

    if roles_added:
        try:
            await member.add_roles(*roles_added, reason=f"Restored roles after {backup_type} removal")
        except Exception as e:
            print(f"[Main Guild Restore Error] {e}")

    # === DELETE BACKUP AFTER SUCCESSFUL RESTORE ===
    if roles_added or True:   # Delete even if no roles were added (cleanup)
        await delete_role_backup(member.id, guild.id, backup_type)

    if roles_added:
        return f"✅ Disciplinary role removed and previous roles restored ({len(roles_added)} roles)."
    else:
        return "✅ Disciplinary role removed. No previous roles found in backup."

async def remove_cross_guild_roles(user_id: int):
    """Remove specific roles from the user in Radio Traffic + Main Server"""
    servers_to_check = {
        RADIO_TRAFFIC_GUILD_ID: CROSS_GUILD_ROLES_TO_REMOVE,
        MAIN_SERVER_GUILD_ID: [MAIN_SERVER_ROLE_TO_MANAGE]
    }

    for guild_id, role_ids in servers_to_check.items():
        other_guild = bot.get_guild(guild_id)
        if not other_guild:
            continue

        other_member = other_guild.get_member(user_id)
        if not other_member:
            try:
                other_member = await other_guild.fetch_member(user_id)
            except:
                continue

        for role_id in role_ids:
            role = other_guild.get_role(role_id)
            if role and role in other_member.roles:
                try:
                    await other_member.remove_roles(role, reason="Police Disciplinary Action (cross-guild)")
                    print(f"[Cross-Guild] Removed {role.name} from {user_id} in {other_guild.name}")
                except Exception as e:
                    print(f"[Cross-Guild] Failed to remove role {role_id}: {e}")


async def restore_cross_guild_roles(user_id: int, backup_type: str):
    """Restore previous roles in Radio Traffic Server + Main Server + delete backup"""
    guilds_to_restore = {
        RADIO_TRAFFIC_GUILD_ID: CROSS_GUILD_ROLES_TO_REMOVE,
        MAIN_SERVER_GUILD_ID: [MAIN_SERVER_ROLE_TO_MANAGE]
    }

    for guild_id, _ in guilds_to_restore.items():
        other_guild = bot.get_guild(guild_id)
        if not other_guild:
            continue

        other_member = other_guild.get_member(user_id)
        if not other_member:
            try:
                other_member = await other_guild.fetch_member(user_id)
            except:
                continue

        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute(
                """SELECT previous_roles FROM role_backups 
                   WHERE user_id = ? AND guild_id = ? AND backup_type = ?""",
                (str(user_id), str(guild_id), backup_type)
            ) as cursor:
                row = await cursor.fetchone()

        if not row or not row[0]:
            continue

        previous_role_ids = [int(rid) for rid in row[0].split(",") if rid.strip()]
        roles_to_add = []

        for rid in previous_role_ids:
            role = other_guild.get_role(rid)
            if role:
                roles_to_add.append(role)

        if roles_to_add:
            try:
                await other_member.add_roles(*roles_to_add, reason=f"Restored roles after {backup_type} removal (cross-guild)")
                
                # === DELETE BACKUP AFTER SUCCESSFUL RESTORE ===
                await delete_role_backup(user_id, guild_id, backup_type)
                
            except Exception as e:
                print(f"[Cross-Guild Restore Error] {other_guild.name}: {e}")

async def apply_police_disciplinary(
    interaction: discord.Interaction,
    member: discord.Member,
    action: str,
    duration: str = None
):
    if not can_use_police_commands(interaction.user):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    guild = interaction.guild

    ver_header = guild.get_role(VERIFICATION_HEADER_ROLE_ID)
    verified = guild.get_role(VERIFIED_ROLE_ID)

    if action == "blacklist":
        target_role_id = POLICE_BARRED_LIST_ROLE_ID
        embed_title = "Police Blacklist Applied"
        embed_color = discord.Color.red()
        is_permanent = True
        backup_type = "blacklist"
    else:
        target_role_id = REMOVAL_COOLDOWN_ROLE_ID
        embed_title = "Police Removal Applied"
        embed_color = discord.Color.orange()
        is_permanent = False
        backup_type = "removal"

    target_role = guild.get_role(target_role_id)
    if not ver_header or not verified or not target_role:
        await interaction.followup.send("❌ Required roles not found in server.")
        return

    keep_roles = [ver_header, verified]

    try:
        # Save current roles BEFORE stripping
        await save_role_backup(member, backup_type)

        # Strip to only verification roles
        await member.edit(roles=keep_roles, reason=f"Police {action} by {interaction.user}")

        if is_permanent:
            await member.add_roles(target_role, reason=f"Police Blacklist - {target_role.name}")
            role_text = f"{target_role.mention} (Permanent)"
        else:
            if not duration:
                await interaction.followup.send("❌ Duration is required.")
                return
            seconds = parse_duration(duration)
            if seconds <= 0:
                await interaction.followup.send("❌ Invalid duration.")
                return
            expires_at = int(time.time()) + seconds
            await member.add_roles(target_role, reason=f"Police Removal - {target_role.name}")
            await add_temp_role(member.id, guild.id, target_role.id, expires_at, interaction.user.id)
            role_text = f"{target_role.mention} (Temporary - {duration})"
            
        await remove_cross_guild_roles(member.id)

        embed = discord.Embed(title=embed_title, color=embed_color)
        embed.add_field(name="Target User", value=f"{member.mention} (`{member.id}`)", inline=False)
        embed.add_field(name="Role Given", value=role_text, inline=True)
        embed.add_field(name="Previous Roles", value="Saved for later restoration", inline=False)
        embed.set_footer(text=f"Action by {interaction.user.display_name}")
        embed.timestamp = discord.utils.utcnow()

        await interaction.followup.send(embed=embed)

    except Exception as e:
        print(f"Error in police {action}: {e}")
        await interaction.followup.send("❌ Something went wrong.")


# ================== DURATION PARSER ==================
def parse_duration(duration: str) -> int:
    match = re.match(r'^(\d+)([mhd])$', duration.lower())
    if not match:
        raise ValueError("Invalid duration")
    amount, unit = match.groups()
    amount = int(amount)
    if unit == 'm': return amount * 60
    if unit == 'h': return amount * 3600
    if unit == 'd': return amount * 86400
    return 0

def parse_loa_duration(duration: str) -> int:
    """Convert '7 days', '2 weeks', '4 weeks' etc. into number of days"""
    duration = duration.lower().strip()

    # Extract the number
    num = int(''.join(filter(str.isdigit, duration)) or 1)

    if "week" in duration:
        return num * 7
    else:
        return num

# ================== VIEWS ==================
class GlobalBanRequestView(discord.ui.View):
    def __init__(self, target_user, reason, requester):
        super().__init__(timeout=None)
        self.target_user = target_user
        self.reason = reason
        self.requester = requester

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ Not allowed", ephemeral=True)
            return

        await interaction.response.defer()

        success = 0
        for guild in interaction.client.guilds:
            try:
                await guild.ban(self.target_user, reason=self.reason)
                success += 1
            except:
                pass

        await add_global_ban(self.target_user.id, self.reason)

        # Update embed with number of servers banned in
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.add_field(name="✅ Accepted By", value=f"{interaction.user.mention}", inline=False)
        embed.add_field(name="Banned In", value=f"{success} servers", inline=True)

        # Remove both buttons and add only "Accepted by" button
        self.clear_items()
        self.add_item(discord.ui.Button(
            label=f"Accepted by {interaction.user.display_name}",
            style=discord.ButtonStyle.green,
            disabled=True
        ))

        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ Not allowed", ephemeral=True)
            return

        await interaction.response.defer()

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.greyple()
        embed.add_field(name="❌ Denied By", value=f"{interaction.user.mention}", inline=False)

        # Remove both buttons and add only "Denied by" button
        self.clear_items()
        self.add_item(discord.ui.Button(
            label=f"Denied by {interaction.user.display_name}",
            style=discord.ButtonStyle.red,
            disabled=True
        ))

        await interaction.message.edit(embed=embed, view=self)

# ================== DATABASE ==================
async def setup_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Global bans table
        await db.execute("""CREATE TABLE IF NOT EXISTS global_bans (
            user_id TEXT PRIMARY KEY,
            reason TEXT,
            timestamp INTEGER
        )""")

        # Temporary roles table (for /temprole, /policeblacklist etc.)
        await db.execute("""CREATE TABLE IF NOT EXISTS temp_roles (
            user_id TEXT,
            guild_id TEXT,
            role_id TEXT,
            expires_at INTEGER,
            added_by TEXT,
            PRIMARY KEY (user_id, guild_id, role_id)
        )""")

        # Active LOAs table
        await db.execute("""CREATE TABLE IF NOT EXISTS active_loas (
            user_id TEXT PRIMARY KEY,
            approved_by TEXT,
            start_time INTEGER,
            end_time INTEGER,
            reason TEXT,
            length TEXT
        )""")

        # NEW: Role backups for /removeblacklist and /removepoliceremoval
        await db.execute("""CREATE TABLE IF NOT EXISTS role_backups (
            user_id TEXT,
            guild_id TEXT,
            backup_type TEXT,
            previous_roles TEXT,
            timestamp INTEGER,
            PRIMARY KEY (user_id, guild_id, backup_type)
        )""")

        await db.commit()

async def add_global_ban(user_id, reason):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO global_bans VALUES (?, ?, ?)", (str(user_id), reason, int(time.time())))
        await db.commit()

async def remove_global_ban(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM global_bans WHERE user_id = ?", (str(user_id),))
        await db.commit()

async def is_banned(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT 1 FROM global_bans WHERE user_id = ?", (str(user_id),)) as cursor:
            return await cursor.fetchone() is not None

async def get_all_bans():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM global_bans") as cursor:
            return await cursor.fetchall()

async def add_temp_role(user_id: int, guild_id: int, role_id: int, expires_at: int, added_by: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""INSERT INTO temp_roles (user_id, guild_id, role_id, expires_at, added_by, added_at)
            VALUES (?, ?, ?, ?, ?, ?)""", (str(user_id), str(guild_id), str(role_id), expires_at, str(added_by), int(time.time())))
        await db.commit()

async def get_user_temp_roles(user_id: int, guild_id: int = None):
    async with aiosqlite.connect(DB_NAME) as db:
        if guild_id:
            query = "SELECT role_id, expires_at FROM temp_roles WHERE user_id = ? AND guild_id = ?"
            params = (str(user_id), str(guild_id))
        else:
            query = "SELECT guild_id, role_id, expires_at FROM temp_roles WHERE user_id = ?"
            params = (str(user_id),)
        async with db.execute(query, params) as cursor:
            return await cursor.fetchall()

async def remove_expired_temp_roles():
    now = int(time.time())
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, guild_id, role_id, user_id FROM temp_roles WHERE expires_at <= ?", (now,)) as cursor:
            expired = await cursor.fetchall()
        for row in expired:
            try:
                guild = bot.get_guild(int(row[1]))
                if guild:
                    member = guild.get_member(int(row[3]))
                    role = guild.get_role(int(row[2]))
                    if member and role:
                        await member.remove_roles(role, reason="Temp role expired")
            except:
                pass
        await db.execute("DELETE FROM temp_roles WHERE expires_at <= ?", (now,))
        await db.commit()

# ================== LOA CLEANUP ==================

async def remove_expired_loas():
    now = int(time.time())
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM active_loas WHERE end_time <= ?", (now,)) as cursor:
            expired = await cursor.fetchall()
        
        for (user_id,) in expired:
            try:
                guild = bot.get_guild(GUILD_ID)
                if guild:
                    member = guild.get_member(int(user_id))
                    loa_role = guild.get_role(LOA_ROLE_ID)
                    if member and loa_role:
                        await member.remove_roles(loa_role, reason="LOA Expired")
            except:
                pass
        
        # Delete expired entries
        await db.execute("DELETE FROM active_loas WHERE end_time <= ?", (now,))
        await db.commit()


async def loa_cleanup_loop():
    await bot.wait_until_ready()
    while True:
        await remove_expired_loas()
        await asyncio.sleep(300)  # Check every 5 minutes

# ================== BOT SETUP ==================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True  
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await setup_db()
    bot.loop.create_task(temp_role_cleanup_loop())
    bot.loop.create_task(loa_cleanup_loop())
    
    # Global sync - makes commands available in ALL servers
    await bot.tree.sync()
    print("✅ Slash commands synced globally")

async def temp_role_cleanup_loop():
    await bot.wait_until_ready()
    while True:
        await remove_expired_temp_roles()
        await asyncio.sleep(60)

async def loa_cleanup_loop():
    await bot.wait_until_ready()
    while True:
        await remove_expired_loas()
        await asyncio.sleep(300)  # Check every 5 minutes

@bot.event
async def on_member_join(member):
    if await is_banned(member.id):
        try:
            await member.ban(reason="Global ban enforcement")
        except:
            pass

@bot.event
async def on_guild_join(guild):
    bans = await get_all_bans()
    for (user_id,) in bans:
        try:
            user = await bot.fetch_user(int(user_id))
            await guild.ban(user, reason="Global ban sync")
        except:
            pass

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    """Remove user from active_loas if LOA role is manually removed"""
    loa_role = after.guild.get_role(LOA_ROLE_ID)
    if not loa_role:
        return

    had_loa = loa_role in before.roles
    has_loa = loa_role in after.roles

    # If LOA role was removed
    if had_loa and not has_loa:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("DELETE FROM active_loas WHERE user_id = ?", (str(after.id),))
            await db.commit()

# ================== COMMANDS ==================

@bot.tree.command(name="globalban", description="Ban a user from all guilds")
@app_commands.describe(user="User to ban", reason="Reason for ban")
async def globalban(interaction: discord.Interaction, user: discord.User, reason: str = "No reason provided"):
    if interaction.user.id not in OWNER_IDS and not is_admin(interaction.user):
        await interaction.response.send_message("❌ Not allowed", ephemeral=True)
        return

    await interaction.response.defer()

    success = 0
    try:
        await add_global_ban(user.id, reason)

        for guild in bot.guilds:
            try:
                # This line now always adds "Global Ban - " for everyone
                await guild.ban(user, reason=f"Global Ban - {reason}")
                success += 1
            except:
                pass

    except Exception as e:
        print(f"Error during globalban: {e}")

    # Logging (already fixed in previous message)
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        try:
            embed = discord.Embed(title="🔨 Global Ban Executed", color=discord.Color.red())
            embed.add_field(name="Target User", value=f"{user} (`{user.id}`)", inline=False)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Banned In", value=f"{success} servers", inline=True)
            embed.add_field(name="Executed By", value=f"{interaction.user} (`{interaction.user.id}`)", inline=False)
            embed.timestamp = discord.utils.utcnow()
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"Failed to log globalban: {e}")

    await interaction.followup.send(f"✅ Banned in {success} guilds")

@bot.tree.command(name="unglobalban", description="Unban a user globally")
@app_commands.describe(user="User to unban", reason="Reason for unban (optional)")
async def unglobalban(interaction: discord.Interaction, user: discord.User, reason: str = "No reason provided"):
    if interaction.user.id not in OWNER_IDS and not is_admin(interaction.user):
        await interaction.response.send_message("❌ Not allowed", ephemeral=True)
        return

    await interaction.response.defer()

    success = 0
    try:
        await remove_global_ban(user.id)

        for guild in bot.guilds:
            try:
                await guild.unban(user, reason=f"Global Unban - {reason}")
                success += 1
            except:
                pass

    except Exception as e:
        print(f"Error during unglobalban: {e}")

    # === LOG TO LOG CHANNEL (works for both Owners and Admins) ===
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        try:
            embed = discord.Embed(title="🔓 Global Unban Executed", color=discord.Color.green())
            embed.add_field(name="Target User", value=f"{user} (`{user.id}`)", inline=False)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Unbanned In", value=f"{success} servers", inline=True)
            embed.add_field(name="Executed By", value=f"{interaction.user} (`{interaction.user.id}`)", inline=False)
            embed.timestamp = discord.utils.utcnow()
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"Failed to log unglobalban: {e}")

    await interaction.followup.send(f"✅ Unbanned in {success} guilds")

@bot.tree.command(name="globalbanrequest", description="Request a global ban")
@app_commands.describe(user="User to ban", reason="Reason")
async def globalbanrequest(interaction: discord.Interaction, user: discord.User, reason: str):
    # Only allow specific roles for global ban requests
    if not any(role.id in GLOBALBAN_REQUEST_ROLE_IDS for role in interaction.user.roles) and interaction.user.id != OWNER_IDS:
        await interaction.response.send_message("❌ You cannot request global bans", ephemeral=True)
        return
    await interaction.response.send_message("✅ Request sent", ephemeral=True)
    embed = discord.Embed(title="📩 Global Ban Request", color=discord.Color.orange())
    embed.add_field(name="Target User", value=f"{user} (`{user.id}`)", inline=False)
    embed.add_field(name="Requested By", value=f"{interaction.user} (`{interaction.user.id}`)", inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.timestamp = discord.utils.utcnow()
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        view = GlobalBanRequestView(user, reason, interaction.user)
        await channel.send(embed=embed, view=view)

@bot.tree.command(name="scamlink", description="Delete user messages and timeout for 24 hours")
@app_commands.describe(user="User who posted the scam link", delete_range="How many hours back to delete messages")
async def scamlink(interaction: discord.Interaction, user: discord.User, delete_range: int = 24):
    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ Not allowed", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    if delete_range > 48:
        delete_range = 48
    success_timeout = 0
    success_messages = 0
    for guild in bot.guilds:
        try:
            member = guild.get_member(user.id)
            if member:
                try:
                    await member.timeout(timedelta(hours=24), reason="Scam link")
                    success_timeout += 1
                except:
                    pass
                cutoff_time = discord.utils.utcnow() - timedelta(hours=delete_range)
                for channel in guild.text_channels:
                    try:
                        async for msg in channel.history(after=cutoff_time, limit=200):
                            if msg.author.id == user.id:
                                await msg.delete()
                                success_messages += 1
                    except:
                        pass
        except:
            pass
    await interaction.followup.send(f"🛑 Scam action complete\n🔇 Timed out in: {success_timeout} servers\n🗑️ Messages deleted: {success_messages}")

# ================== TEMPORARY ROLES ==================
@bot.tree.command(name="temprole", description="Add or remove temporary roles")
@app_commands.describe(
    action="add or remove",
    user="Target user",
    role="Role to add/remove",
    duration="Duration (e.g. 1h, 30m, 7d) - only for add"
)
@app_commands.choices(action=[
    app_commands.Choice(name="Add", value="add"),
    app_commands.Choice(name="Remove", value="remove")
])
async def temprole(
    interaction: discord.Interaction,
    action: str,
    user: discord.Member,           # Changed to Member for consistency
    role: discord.Role,
    duration: str = None
):
    # Permission check (same as /role)
    if not can_manage_roles(interaction.user, interaction.guild):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    action = action.lower()

    if action not in ["add", "remove"]:
        await interaction.response.send_message("❌ Action must be `add` or `remove`", ephemeral=True)
        return

    # === NEW: Hierarchy Check (Only OWNER_IDS can bypass) ===
    if role.position >= interaction.user.top_role.position:
        if interaction.user.id not in OWNER_IDS:
            await interaction.response.send_message(
                f"❌ You cannot manage {role.mention} because it is higher than or equal to your highest role.",
                ephemeral=True
            )
            return

    await interaction.response.defer(thinking=True)

    guild = interaction.guild
    member = guild.get_member(user.id)
    if not member:
        await interaction.followup.send("❌ User is not in this server.", ephemeral=True)
        return

    try:
        if action == "add":
            if not duration:
                await interaction.followup.send("❌ Please provide a duration (e.g. 12h, 7d)", ephemeral=True)
                return

            try:
                seconds = parse_duration(duration)
                if seconds <= 0:
                    raise ValueError
            except:
                await interaction.followup.send("❌ Invalid duration format. Use: 30m, 2h, 5d", ephemeral=True)
                return

            expires_at = int(time.time()) + seconds

            await member.add_roles(role, reason=f"Temporary role • {interaction.user}")
            await add_temp_role(user.id, guild.id, role.id, expires_at, interaction.user.id)

            expires_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)
            embed = discord.Embed(title="✅ Temporary Role Added", color=discord.Color.green())
            embed.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
            embed.add_field(name="Role", value=role.mention, inline=False)
            embed.add_field(name="Expires", value=discord.utils.format_dt(expires_dt, style='R'), inline=False)
            await interaction.followup.send(embed=embed)

        elif action == "remove":
            # Delete from database
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute(
                    "DELETE FROM temp_roles WHERE user_id = ? AND guild_id = ? AND role_id = ?",
                    (str(user.id), str(guild.id), str(role.id))
                )
                await db.commit()

            if role in member.roles:
                await member.remove_roles(role, reason="Temporary role manually removed")

            await interaction.followup.send(f"✅ Removed temporary role **{role.name}** from {user.mention}")

    except Exception as e:
        print(f"❌ Temprole error: {e}")
        await interaction.followup.send("❌ Something went wrong.", ephemeral=True)


@bot.tree.command(name="temproles", description="Show all temporary roles for a user")
@app_commands.describe(user="User to check")
async def temproles(interaction: discord.Interaction, user: discord.User):
    if not has_request_role(interaction.user) and not is_admin(interaction.user):
        await interaction.response.send_message("❌ Not allowed", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    rows = await get_user_temp_roles(user.id, interaction.guild.id)

    if not rows:
        # Double-check with no guild filter in case of bug
        all_rows = await get_user_temp_roles(user.id)
        if all_rows:
            return await interaction.followup.send(f"✅ **{user}** has temporary roles but not in this server.", ephemeral=True)
        
        return await interaction.followup.send(f"✅ **{user}** has no active temporary roles in this server.", ephemeral=True)

    embed = discord.Embed(title=f"Temporary Roles for {user}", color=discord.Color.blue())
    embed.set_thumbnail(url=user.display_avatar.url)

    for role_id_str, expires_at in rows:
        role = interaction.guild.get_role(int(role_id_str))
        role_name = role.name if role else f"Deleted Role ({role_id_str})"
        expires_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)
        expires = discord.utils.format_dt(expires_dt, style='R')
        embed.add_field(name=role_name, value=f"Expires: {expires}", inline=False)

    await interaction.followup.send(embed=embed, ephemeral=True)

# ================== LOA REQUEST ==================

LOA_ROLE_ID = 1457118167204630724

class LOARequestView(discord.ui.View):
    def __init__(self, requester: discord.Member, reason: str, length: str):
        super().__init__(timeout=None)
        self.requester = requester
        self.reason = reason
        self.length = length

    def can_manage_loa(self, user: discord.Member) -> bool:
        if user.id in OWNER_IDS or any(role.id in ADMIN_ROLE_IDS for role in user.roles):
            return True
        return any(role.id == LOA_TRACKER_ROLE_ID for role in user.roles)

    @discord.ui.button(label="Approve LOA", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.can_manage_loa(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to approve LOAs.", ephemeral=True)
            return

        await interaction.response.defer()

        guild = interaction.guild
        member = guild.get_member(self.requester.id)
        loa_role = guild.get_role(LOA_ROLE_ID)

        # Calculate when the LOA should end
        days = parse_loa_duration(self.length)
        end_time = int(time.time()) + (days * 86400)

        if member and loa_role:
            try:
                await member.add_roles(loa_role, reason=f"LOA Approved • {self.length}")

                # === THIS IS THE MISSING PART ===
                # Save the LOA to the database so /activeloas can see it
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("""INSERT OR REPLACE INTO active_loas 
                        (user_id, approved_by, start_time, end_time, reason, length)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                        (str(self.requester.id), str(interaction.user.id), 
                         int(time.time()), end_time, self.reason, self.length))
                    await db.commit()

            except Exception as e:
                print(f"LOA approve error: {e}")

        # Update main embed
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.set_field_at(3, name="Status", value=f"Approved by {interaction.user.mention}", inline=False)
        embed.set_footer(text=f"UKRP LOA Request - Approved")

        self.clear_items()
        self.add_item(discord.ui.Button(
            label=f"LOA Approved by {interaction.user.display_name}", 
            style=discord.ButtonStyle.green, 
            disabled=True
        ))

        await interaction.message.edit(embed=embed, view=self)

        # === Send Log to LOA Log Channel ===
        log_channel = bot.get_channel(LOA_LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(
                title="UKRP LOA Request Log",
                color=discord.Color.green(),
                description=f"{self.requester.mention}'s LOA request has been accepted by {interaction.user.mention}"
            )
            log_embed.add_field(name="Duration", value=self.length, inline=False)
            log_embed.add_field(name="Reason", value=self.reason, inline=False)
            log_embed.add_field(name="", value=f"Today at {discord.utils.format_dt(discord.utils.utcnow(), style='t')}", inline=False)
            
            await log_channel.send(embed=log_embed)

    @discord.ui.button(label="Deny LOA", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.can_manage_loa(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to deny LOAs.", ephemeral=True)
            return

        await interaction.response.defer()

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.set_field_at(3, name="Status", value=f"Denied by {interaction.user.mention}", inline=False)
        embed.set_footer(text=f"UKRP LOA Request - Denied")

        self.clear_items()
        self.add_item(discord.ui.Button(
            label=f"LOA Denied by {interaction.user.display_name}", 
            style=discord.ButtonStyle.red, 
            disabled=True
        ))

        await interaction.message.edit(embed=embed, view=self)


@bot.tree.command(name="loarequest", description="Submit a Leave of Absence request")
@app_commands.describe(
    reason="Reason for LOA",
    length="Length of LOA (e.g. 1 week, 2 weeks, 10 days)"
)
async def loarequest(interaction: discord.Interaction, reason: str, length: str):
    member = interaction.guild.get_member(interaction.user.id)

    # Check for restricted roles
    if member:
        if any(role.id == INACTIVITY_WARNING_ROLE_ID for role in member.roles):
            await interaction.response.send_message("❌ You cannot request LOA while having an Inactivity Warning.", ephemeral=True)
            return
        if any(role.id == LOA_COOLDOWN_ROLE_ID for role in member.roles):
            await interaction.response.send_message("❌ You are currently on LOA Cooldown and cannot request a new LOA.", ephemeral=True)
            return

    # Check permission to request
    if not has_request_role(interaction.user) and not is_admin(interaction.user):
        await interaction.response.send_message("❌ You cannot request LOAs", ephemeral=True)
        return

    # Validate duration
    try:
        days = parse_loa_duration(length)

        if days < 7:
            await interaction.response.send_message("❌ Minimum LOA is 7 days.", ephemeral=True)
            return
        if days > 28:
            await interaction.response.send_message("❌ Maximum LOA is 4 weeks (28 days).", ephemeral=True)
            return

    except:
        await interaction.response.send_message("❌ Invalid format. Use: `7 days`, `2 weeks`, `10 days`, `4 weeks`", ephemeral=True)
        return

    await interaction.response.send_message("✅ LOA request submitted!", ephemeral=True)

    embed = discord.Embed(title="UKRP LOA Request", color=discord.Color.orange())
    embed.add_field(name="Submitted By", value=interaction.user.mention, inline=False)
    embed.add_field(name="Duration", value=length, inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Status", value="Pending", inline=False)
    embed.set_footer(text="UKRP LOA Request - Pending")
    embed.timestamp = datetime.now(zoneinfo.ZoneInfo("Europe/London"))

    view = LOARequestView(interaction.user, reason, length)
    await interaction.channel.send(embed=embed, view=view)

@bot.tree.command(name="activeloas", description="Show all users currently on LOA")
async def activeloas(interaction: discord.Interaction):
    # Only LOA Tracker + Admins can use this command
    if not (is_admin(interaction.user) or 
            any(role.id == LOA_TRACKER_ROLE_ID for role in interaction.user.roles)):
        await interaction.response.send_message("❌ Only LOA Trackers can view active LOAs.", ephemeral=True)
        return

    await interaction.response.defer()

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("""SELECT user_id, approved_by, end_time 
                                FROM active_loas ORDER BY end_time""") as cursor:
            active_loas = await cursor.fetchall()

    if not active_loas:
        return await interaction.followup.send("✅ No users are currently on LOA.")

    embed = discord.Embed(title="Current Active LOAs", color=discord.Color.blue())

    for user_id, approved_by, end_time in active_loas:
        member = interaction.guild.get_member(int(user_id))
        if not member:
            continue

        name = member.display_name
        end_dt = datetime.fromtimestamp(end_time, tz=timezone.utc)
        time_left = discord.utils.format_dt(end_dt, style='R')
        approver = f"<@{approved_by}>"

        embed.add_field(
            name=name,
            value=f"**Approved by:** {approver}\n**Ends:** {time_left}",
            inline=False
        )

    embed.set_footer(text=f"Total on LOA: {len(active_loas)}")
    embed.timestamp = datetime.now(zoneinfo.ZoneInfo("Europe/London"))

    await interaction.followup.send(embed=embed)

# ================== ROLE MANAGEMENT ==================

@bot.tree.command(name="role", description="Add or remove a role from a user")
@app_commands.describe(
    action="add or remove",
    user="The user to modify",
    role="The role to add or remove",
    reason="Reason (required only when adding a role to yourself)"
)
@app_commands.choices(action=[
    app_commands.Choice(name="Add", value="add"),
    app_commands.Choice(name="Remove", value="remove")
])
async def role(
    interaction: discord.Interaction,
    action: str,
    user: discord.Member,
    role: discord.Role,
    reason: str = None
):
    # Permission check (your existing per-guild system)
    if not can_manage_roles(interaction.user, interaction.guild):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    action = action.lower()

    # Require reason when adding a role to yourself
    if action == "add" and user.id == interaction.user.id and not reason:
        await interaction.response.send_message(
            "❌ You must provide a reason when adding a role to yourself.",
            ephemeral=True
        )
        return

    # === NEW: Hierarchy Check ===
    # Only users in OWNER_IDS can bypass this
    if role.position >= interaction.user.top_role.position:
        if interaction.user.id not in OWNER_IDS:
            await interaction.response.send_message(
                f"❌ You cannot manage {role.mention} because it is higher than or equal to your highest role.",
                ephemeral=True
            )
            return

    await interaction.response.defer(thinking=True)

    try:
        if action == "add":
            if role in user.roles:
                return await interaction.followup.send(f"❌ {user.mention} already has the role {role.mention}.")

            await user.add_roles(role, reason=reason or f"Added by {interaction.user}")

            embed = discord.Embed(color=discord.Color.green())
            embed.description = f"✅ Added {role.mention} to {user.mention}."
            await interaction.followup.send(embed=embed)

        elif action == "remove":
            if role not in user.roles:
                return await interaction.followup.send(f"❌ {user.mention} does not have the role {role.mention}.")

            await user.remove_roles(role, reason=f"Removed by {interaction.user}")

            embed = discord.Embed(color=discord.Color.red())
            embed.description = f"❌ Removed {role.mention} from {user.mention}."
            await interaction.followup.send(embed=embed)

    except discord.Forbidden:
        await interaction.followup.send("❌ I don't have permission to manage that role.")
    except Exception as e:
        print(f"Role command error: {e}")
        await interaction.followup.send("❌ Something went wrong.")

@bot.tree.command(name="policeblacklist", description="Blacklist a user (strip roles + permanent Police Barred List)")
@app_commands.describe(user="Target user")
async def policeblacklist(interaction: discord.Interaction, user: discord.Member):
    await apply_police_disciplinary(interaction, user, "blacklist")


@bot.tree.command(name="policeremoval", description="Apply police removal (strip roles + temporary Removal Cooldown)")
@app_commands.describe(user="Target user", duration="Duration (e.g. 28d)")
async def policeremoval(interaction: discord.Interaction, user: discord.Member, duration: str):
    await apply_police_disciplinary(interaction, user, "removal", duration)


@bot.tree.command(name="removeblacklist", description="Remove Police Barred List role and restore previous roles in all servers")
@app_commands.describe(user="Target user")
async def removeblacklist(interaction: discord.Interaction, user: discord.Member):
    if not can_use_police_commands(interaction.user):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    # Restore in main guild
    main_result = await restore_from_backup(user, "blacklist", POLICE_BARRED_LIST_ROLE_ID)

    # Restore in Radio Traffic + Main Server
    await restore_cross_guild_roles(user.id, "blacklist")

    embed = discord.Embed(title="Police Blacklist Removed", color=discord.Color.green())
    embed.add_field(name="Target User", value=f"{user.mention} (`{user.id}`)", inline=False)
    embed.add_field(name="Main Server", value=main_result, inline=False)
    embed.add_field(name="Radio Traffic + Main Server", value="Roles restored from backup", inline=False)
    embed.set_footer(text=f"Action by {interaction.user.display_name}")
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="removepoliceremoval", description="Remove Removal Cooldown role and restore previous roles in all servers")
@app_commands.describe(user="Target user")
async def removepoliceremoval(interaction: discord.Interaction, user: discord.Member):
    if not can_use_police_commands(interaction.user):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    # Restore in main guild
    main_result = await restore_from_backup(user, "removal", REMOVAL_COOLDOWN_ROLE_ID)

    # Restore in Radio Traffic + Main Server
    await restore_cross_guild_roles(user.id, "removal")

    embed = discord.Embed(title="Police Removal Reversed", color=discord.Color.green())
    embed.add_field(name="Target User", value=f"{user.mention} (`{user.id}`)", inline=False)
    embed.add_field(name="Main Server", value=main_result, inline=False)
    embed.add_field(name="Radio Traffic + Main Server", value="Roles restored from backup", inline=False)
    embed.set_footer(text=f"Action by {interaction.user.display_name}")
    await interaction.followup.send(embed=embed)

# ================== TRAINING COMMAND ==================

class TrainingView(discord.ui.View):
    def __init__(self, division: str, time: str, host: discord.Member):
        super().__init__(timeout=None)
        self.division = division
        self.time = time
        self.host = host
        self.co_hosts = []
        self.attendees = []
        self.status = "Upcoming"
        self.ended_by = None

    def create_embed(self):
        if self.division == "Response":
            title = f"Response Training — {self.status}"
            description = f"A training for the Response Division will be held at {self.time}. Please make sure you are in-game, on the Police team in your uniform and sat down in the briefing room."
            vc_name = "Response Training"
            vc_link = f"https://discord.com/channels/1457118167078801631/{RESPONSE_TRAINING_VC_ID}"
        else:
            title = f"Roads Training — {self.status}"
            description = f"A training for the Roads Policing Unit will be held at {self.time}. Please make sure you are in-game and ready."
            vc_name = "Roads Training"
            vc_link = "https://discord.com/channels/1457118167078801631/REPLACE_WITH_ROADS_VC_ID"

        color = discord.Color.orange()
        if self.status == "In Progress":
            color = discord.Color.green()
        elif self.status == "Ended":
            color = discord.Color.red()

        embed = discord.Embed(title=title, description=description, color=color)

        host_text = f"{self.host.mention}"
        if self.co_hosts:
            host_text += "\n" + "\n".join([c.mention for c in self.co_hosts])
        embed.add_field(name="Hosts", value=host_text, inline=False)

        if self.attendees:
            embed.add_field(name="Attendees", value="\n".join([a.mention for a in self.attendees]), inline=False)
        else:
            embed.add_field(name="Attendees", value="No one yet", inline=False)

        embed.add_field(name="Active Staff VC", value=f"{vc_name}\n{vc_link}", inline=False)

        if self.ended_by:
            embed.add_field(name="Ended By", value=self.ended_by.mention, inline=False)

        return embed

    def disable_attendance_buttons(self):
        for child in self.children:
            if child.label in ["Attend as Co-Host", "Attending"]:
                child.disabled = True

    @discord.ui.button(label="Start", style=discord.ButtonStyle.green, emoji="▶️")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(r.id == ENTRY_PROGRAMME_INSTRUCTOR_ROLE_ID for r in interaction.user.roles):
            await interaction.response.send_message("❌ Only Entry Programme Instructors can start the training.", ephemeral=True)
            return

        if self.status != "Upcoming":
            await interaction.response.send_message("❌ Training has already started or ended.", ephemeral=True)
            return

        self.status = "In Progress"
        button.disabled = True
        self.disable_attendance_buttons()

        await interaction.message.edit(embed=self.create_embed(), view=self)
        await interaction.response.send_message("Training has started!", ephemeral=True)

    @discord.ui.button(label="Attend as Co-Host", style=discord.ButtonStyle.blurple, emoji="👥")
    async def cohost_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.status != "Upcoming":
            await interaction.response.send_message("❌ You can no longer join as Co-Host.", ephemeral=True)
            return

        if not any(r.id == ENTRY_PROGRAMME_INSTRUCTOR_ROLE_ID for r in interaction.user.roles):
            await interaction.response.send_message("❌ Only Entry Programme Instructors can be Co-Hosts.", ephemeral=True)
            return

        if len(self.co_hosts) >= 3:
            await interaction.response.send_message("❌ Maximum of 3 Co-Hosts allowed.", ephemeral=True)
            return

        if interaction.user in self.co_hosts:
            await interaction.response.send_message("❌ You are already a Co-Host.", ephemeral=True)
            return

        self.co_hosts.append(interaction.user)
        await interaction.message.edit(embed=self.create_embed(), view=self)
        await interaction.response.send_message("You are now a Co-Host!", ephemeral=True)

    @discord.ui.button(label="Attending", style=discord.ButtonStyle.green, emoji="✅")
    async def attending_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.status != "Upcoming":
            await interaction.response.send_message("❌ You can no longer mark yourself as attending.", ephemeral=True)
            return

        if not any(r.id == STUDENT_CONSTABLE_ROLE_ID for r in interaction.user.roles):
            await interaction.response.send_message("❌ Only Student Constables can mark themselves as attending.", ephemeral=True)
            return

        if interaction.user in self.attendees:
            await interaction.response.send_message("❌ You have already marked yourself as attending.", ephemeral=True)
            return

        self.attendees.append(interaction.user)
        await interaction.message.edit(embed=self.create_embed(), view=self)
        await interaction.response.send_message("You are now marked as attending!", ephemeral=True)

    @discord.ui.button(label="End Training", style=discord.ButtonStyle.red, emoji="🛑")
    async def end_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.status == "Ended":
            await interaction.response.send_message("❌ Training has already ended.", ephemeral=True)
            return

        self.status = "Ended"
        self.ended_by = interaction.user

        for child in self.children:
            child.disabled = True

        await interaction.message.edit(embed=self.create_embed(), view=self)
        await interaction.response.send_message("Training has ended.", ephemeral=True)


# ================== SLASH COMMAND ==================
@app_commands.describe(
    division="Which division is the training for?",
    time="When is the training? (e.g. Tonight at 8pm)"
)
@app_commands.choices(division=[
    app_commands.Choice(name="Response Division", value="Response"),
    app_commands.Choice(name="Roads Policing Unit", value="Roads")
])
async def training(interaction: discord.Interaction, division: str, time: str):
    # Permission check
    if not any(r.id in [ENTRY_PROGRAMME_INSTRUCTOR_ROLE_ID, ROADS_INSTRUCTOR_ROLE_ID] 
               for r in interaction.user.roles):
        await interaction.response.send_message(
            "❌ Only Entry Programme Instructors and Roads Instructors can use this command.", 
            ephemeral=True
        )
        return

    view = TrainingView(division, time, interaction.user)
    embed = view.create_embed()

    # Ping the required roles above the embed
    ping = f"<@&{ENTRY_PROGRAMME_INSTRUCTOR_ROLE_ID}> <@&{STUDENT_CONSTABLE_ROLE_ID}>"

    channel = bot.get_channel(TRAINING_ANNOUNCEMENTS_CHANNEL_ID)
    await channel.send(content=ping, embed=embed, view=view)

    await interaction.response.send_message("Training announcement has been posted!", ephemeral=True)

# ================== RUN BOT ==================
bot.run(TOKEN)