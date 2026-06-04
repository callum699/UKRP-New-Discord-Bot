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
OWNER_ID = 738790396511125654
GUILD_ID = 1457118167078801631

REQUEST_ROLE_IDS = [1460998934842441809, 1457118167204630725, 1457118167108161540]
ADMIN_ROLE_IDS = [1457118167204630728]
LOA_TRACKER_ROLE_ID =  1457118167095841075

LOA_LOG_CHANNEL_ID = 1511706584189767700

INACTIVITY_WARNING_ROLE_ID = 1457118167091642440
LOA_COOLDOWN_ROLE_ID = 1457118167108161545

LOG_CHANNEL_ID = 1504537214829461677
DB_NAME = "globalbans.db"

# ================== PERMISSION HELPERS ==================
def has_request_role(user):
    return any(role.id in REQUEST_ROLE_IDS for role in user.roles)

def is_admin(user):
    if user.id == OWNER_ID:
        return True
    return any(role.id in ADMIN_ROLE_IDS for role in user.roles)

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
    duration = duration.lower()
    if "week" in duration:
        num = int(''.join(filter(str.isdigit, duration)) or 1)
        return num * 7
    else:
        num = int(''.join(filter(str.isdigit, duration)) or 1)
        return num

# ================== VIEWS ==================
class GlobalBanRequestView(discord.ui.View):
    def __init__(self, target_user, reason, requester):
        super().__init__(timeout=None)
        self.target_user = target_user
        self.reason = reason
        self.requester = requester

    async def disable_buttons(self):
        for item in self.children:
            item.disabled = True

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.green)
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
        await self.disable_buttons()
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.add_field(name="✅ Accepted By", value=f"{interaction.user} (`{interaction.user.id}`)", inline=False)
        embed.timestamp = discord.utils.utcnow()
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="❌ Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ Not allowed", ephemeral=True)
            return
        await self.disable_buttons()
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.greyple()
        embed.add_field(name="❌ Denied By", value=f"{interaction.user} (`{interaction.user.id}`)", inline=False)
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.edit_message(embed=embed, view=self)

# ================== DATABASE ==================
async def setup_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS global_bans (user_id TEXT PRIMARY KEY, reason TEXT, banned_at INTEGER)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS temp_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, guild_id TEXT,
            role_id TEXT, expires_at INTEGER, added_by TEXT, added_at INTEGER)""")
        
        await db.execute("""CREATE TABLE IF NOT EXISTS active_loas (
            user_id TEXT PRIMARY KEY,
            approved_by TEXT,
            start_time INTEGER,
            end_time INTEGER,
            reason TEXT,
            length TEXT
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
    if interaction.user.id != OWNER_ID and not is_admin(interaction.user):
        await interaction.response.send_message("❌ Not allowed", ephemeral=True)
        return
    await interaction.response.defer()
    success = 0
    try:
        await add_global_ban(user.id, reason)
        for guild in bot.guilds:
            try:
                await guild.ban(user, reason=reason)
                success += 1
            except:
                pass
    except Exception as e:
        print(f"❌ Error during globalban: {e}")
    await interaction.followup.send(f"✅ Banned in {success} guilds")

@bot.tree.command(name="unglobalban", description="Unban a user globally")
async def unglobalban(interaction: discord.Interaction, user: discord.User):
    if interaction.user.id != OWNER_ID and not is_admin(interaction.user):
        await interaction.response.send_message("❌ Not allowed", ephemeral=True)
        return
    await interaction.response.defer()
    success = 0
    try:
        await remove_global_ban(user.id)
        for guild in bot.guilds:
            try:
                await guild.unban(user)
                success += 1
            except:
                pass
    except Exception as e:
        print(f"❌ Error during unglobalban: {e}")
    await interaction.followup.send(f"✅ Unbanned in {success} guilds")

@bot.tree.command(name="globalbanrequest", description="Request a global ban")
@app_commands.describe(user="User to ban", reason="Reason")
async def globalbanrequest(interaction: discord.Interaction, user: discord.User, reason: str):
    if not has_request_role(interaction.user) and interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ You cannot request bans", ephemeral=True)
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
    user: discord.User,
    role: discord.Role,
    duration: str = None
):
    # No code permission check - Discord handles it
    action = action.lower()
    if action not in ["add", "remove"]:
        await interaction.response.send_message("❌ Action must be `add` or `remove`", ephemeral=True)
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
        if user.id == OWNER_ID or any(role.id in ADMIN_ROLE_IDS for role in user.roles):
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

        if member and loa_role:
            try:
                await member.add_roles(loa_role, reason=f"LOA Approved • {self.length}")
            except:
                pass

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
        await interaction.response.send_message("❌ Invalid format. Use: `1 week`, `10 days`, `3 weeks`", ephemeral=True)
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


# ================== RUN BOT ==================
bot.run(TOKEN)