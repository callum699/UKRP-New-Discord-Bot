import discord
from discord.ext import commands
from discord import app_commands

import aiosqlite
import time
import asyncio
import re
from datetime import timedelta, datetime, timezone
import zoneinfo
import traceback
import aiohttp

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
LOA_TRACKER_ROLE_ID = 1457118167095841075
INACTIVITY_WARNING_ROLE_ID = 1457118167091642440
LOA_COOLDOWN_ROLE_ID = 1457118167108161545

POLICE_COMMAND_ROLE_IDS = [
    1457118167204630725,   # Gold Command
    1460998934842441809    # Professional Standards
]

VERIFICATION_HEADER_ROLE_ID = 1461656344510730383
VERIFIED_ROLE_ID = 1457118167108161542

POLICE_BARRED_LIST_ROLE_ID = 1457118167091642449
REMOVAL_COOLDOWN_ROLE_ID = 1457118167078801640

RADIO_TRAFFIC_GUILD_ID = 1457403990433206344
CROSS_GUILD_ROLES_TO_REMOVE = [
    1457403990449852427,   # Police Personnel
    1497974641292214363,   # EOC Operator
    1509223811306881286,   # EOC Manager
    1457403990458499318,   # RTO Ranking Permissions
    1457403990458499319,   # ✰✰ Police Service High Command ✰✰
    1466005018393055253,   # Professional Standards
    1504096735402922065    # ✰✰✰ Police Service Gold Command ✰✰✰
]

ENTRY_PROGRAMME_INSTRUCTOR_ROLE_ID = 1457118167095841079
ROADS_INSTRUCTOR_ROLE_ID           = 1510303284299304961
RESPONSE_TRAINEE_ROLE_ID = 1505522666369712160
ROADS_TRAINEE_ROLE_ID    = 1519416148926402632

TRAINING_ANNOUNCEMENTS_CHANNEL_ID  = 1457118170983956611
TRAINING_LOGS_CHANNEL_ID = 1457118171181093098
RESPONSE_TRAINING_VC_ID = 1457118171181093100
ROADS_TRAINING_VC_ID = 1519410873700192286

MAIN_SERVER_GUILD_ID = 1452412377034264576
MAIN_SERVER_ROLE_TO_MANAGE = 1452412377101238346

ROLE_COMMAND_ALLOWED_ROLES = {
    1452412377034264576: [
        "UK:RP | Owner",
        "UK:RP | Co-Owner",
        "UK:RP | Community Manager",
        "UK:RP | Management Team",
        "UK:RP | Trial Management"
    ],
    1457403990433206344: [
        "RTO Ranking Permissions"
    ],
    1457118167078801631: [
        "● Discord Ranking Permissions ●"
    ]
}

LOA_LOG_CHANNEL_ID = 1511706584189767700
LOG_CHANNEL_ID = 1504537214829461677
LOA_ROLE_ID = 1457118167204630724

DB_NAME = "globalbans.db"

# ================== ROBLOX RANKING ==================
ROBLOX_API_KEY = os.getenv("ROBLOX_API_KEY")
ROBLOX_GROUP_ID = 767871226

GROUP_RANKING_PERMISSIONS_ROLE_ID = 1457118167204630722

# Rank number → Discord Role ID
ROBLOX_RANK_TO_DISCORD_ROLE = {
    2:  1457118167196504127,  # Student Constable
    5:  1457118167196504128,  # Constable
    10: 1457118167196504129,  # Sergeant
    15: 1457118167196504130,  # Inspector
    20: 1457118167196504131,  # Chief Inspector
    25: 1457118167196504132,  # Superintendent
    30: 1457118167196504133,  # Chief Superintendent
    35: 1457118167204630726,  # Assistant Chief Constable
    40: 1457118167204630727,  # Deputy Chief Constable
    45: 1457118167204630728,  # Chief Constable
}

# Rank number → Rank Name (for display)
ROBLOX_RANK_NAMES = {
    2:  "Student Constable",
    5:  "Constable",
    10: "Sergeant",
    15: "Inspector",
    20: "Chief Inspector",
    25: "Superintendent",
    30: "Chief Superintendent",
    35: "Assistant Chief Constable",
    40: "Deputy Chief Constable",
    45: "Chief Constable",
}

# Sorted list of rank numbers (lowest → highest) for promote/demote
SORTED_RANKS = sorted(ROBLOX_RANK_NAMES.keys())

# ================== PERMISSION HELPERS ==================
def has_request_role(user):
    return any(role.id in REQUEST_ROLE_IDS for role in user.roles)

def is_admin(user):
    if user.id in OWNER_IDS:
        return True
    return any(role.id in ADMIN_ROLE_IDS for role in user.roles)

def can_manage_roles(user: discord.Member, guild: discord.Guild) -> bool:
    if is_admin(user):
        return True
    allowed_role_names = ROLE_COMMAND_ALLOWED_ROLES.get(guild.id, [])
    for role_name in allowed_role_names:
        role = discord.utils.get(guild.roles, name=role_name)
        if role and role in user.roles:
            return True
    return False

def can_use_police_commands(user: discord.Member) -> bool:
    if is_admin(user):
        return True
    return any(role.id in POLICE_COMMAND_ROLE_IDS for role in user.roles)

# ================== ROLE BACKUP SYSTEM ==================
async def save_role_backup(member: discord.Member, backup_type: str):
    guild = member.guild
    role_ids = [str(r.id) for r in member.roles if r != guild.default_role]
    await _save_backup_to_db(str(member.id), str(guild.id), backup_type, ",".join(role_ids))

    other_guild = bot.get_guild(RADIO_TRAFFIC_GUILD_ID)
    if other_guild:
        other_member = other_guild.get_member(member.id)
        if other_member:
            other_role_ids = [str(r.id) for r in other_member.roles if r != other_guild.default_role]
            await _save_backup_to_db(str(member.id), str(other_guild.id), backup_type, ",".join(other_role_ids))

    main_guild = bot.get_guild(MAIN_SERVER_GUILD_ID)
    if main_guild:
        main_member = main_guild.get_member(member.id)
        if main_member:
            main_role_ids = [str(r.id) for r in main_member.roles if r != main_guild.default_role]
            await _save_backup_to_db(str(member.id), str(main_guild.id), backup_type, ",".join(main_role_ids))

async def delete_role_backup(user_id: int, guild_id: int, backup_type: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """DELETE FROM role_backups 
               WHERE user_id = ? AND guild_id = ? AND backup_type = ?""",
            (str(user_id), str(guild_id), backup_type)
        )
        await db.commit()

async def _save_backup_to_db(user_id: str, guild_id: str, backup_type: str, roles_str: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """INSERT OR REPLACE INTO role_backups 
               (user_id, guild_id, backup_type, previous_roles, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, guild_id, backup_type, roles_str, int(time.time()))
        )
        await db.commit()

async def get_roblox_id_from_discord(discord_user_id: int) -> int | None:
    """Look up Roblox ID using Bloxlink"""
    url = f"https://api.blox.link/v4/public/guilds/{GUILD_ID}/discord-to-roblox/{discord_user_id}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return int(data.get("robloxID") or data.get("robloxId") or 0) or None
    except Exception as e:
        print(f"Bloxlink lookup error: {e}")
    return None

async def get_roblox_avatar(roblox_id: int):
    url = (
        "https://thumbnails.roblox.com/v1/users/avatar-headshot"
        f"?userIds={roblox_id}&size=420x420&format=Png&isCircular=false"
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                items = data.get("data") or []
                if not items:
                    return None
                return items[0].get("imageUrl")
    except Exception as e:
        print(f"Avatar lookup error: {e}")
        return None

async def get_roblox_id_from_username(username: str):
    """Resolve a Roblox username to a user ID."""
    username = username.strip().lstrip("@")
    if not username:
        return None

    url = "https://users.roblox.com/v1/usernames/users"
    payload = {"usernames": [username], "excludeBannedUsers": False}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                users = data.get("data") or []
                if not users:
                    return None
                return int(users[0]["id"])
    except Exception as e:
        print(f"Roblox username lookup error: {e}")
        return None


async def resolve_roblox_id(discord_user: discord.Member, roblox_username: str = None):
    """
    Prefer Bloxlink. If that fails, use the optional Roblox username.
    Returns (roblox_id, source) or (None, error_message)
    """
    roblox_id = await get_roblox_id_from_discord(discord_user.id)
    if roblox_id:
        return roblox_id, "Bloxlink"

    if roblox_username:
        roblox_id = await get_roblox_id_from_username(roblox_username)
        if roblox_id:
            return roblox_id, f"username {roblox_username}"
        return None, f"Could not find Roblox user `{roblox_username}`."

    return None, (
        f"Could not find a linked Roblox account for {discord_user.mention}.\n"
        "They are not verified with Bloxlink. Run the command again and fill in **roblox_username**."
    )

async def set_roblox_rank(roblox_user_id: int, rank_number: int):
    """Set a user's rank in the Roblox group using a User API key."""
    if not ROBLOX_API_KEY:
        return False, "ROBLOX_API_KEY is not set in .env"

    rank_name = ROBLOX_RANK_NAMES.get(rank_number)
    if not rank_name:
        return False, f"Unknown rank number {rank_number}"

    headers = {"x-api-key": ROBLOX_API_KEY}
    json_headers = {**headers, "Content-Type": "application/json"}

    try:
        async with aiohttp.ClientSession() as session:
            # 1. Find the Roblox role ID by name
            roles_url = f"https://apis.roblox.com/cloud/v2/groups/{ROBLOX_GROUP_ID}/roles?maxPageSize=50"
            async with session.get(roles_url, headers=headers) as resp:
                text = await resp.text()
                if resp.status != 200:
                    return False, f"Could not list roles ({resp.status}): {text[:300]}"
                roles = (await resp.json()).get("groupRoles") or []

            role_id = None
            for role in roles:
                if (role.get("displayName") or role.get("name") or "").lower() == rank_name.lower():
                    path = role.get("path") or ""
                    role_id = path.split("/")[-1] if path else str(role.get("id"))
                    break

            if not role_id:
                return False, f"Could not find Roblox role named '{rank_name}'."

            # 2. Find this user's membership ID
            filter_q = f"user == 'users/{roblox_user_id}'"
            memberships_url = (
                f"https://apis.roblox.com/cloud/v2/groups/{ROBLOX_GROUP_ID}/memberships"
                f"?maxPageSize=10&filter={filter_q}"
            )
            async with session.get(memberships_url, headers=headers) as resp:
                text = await resp.text()
                if resp.status != 200:
                    return False, f"Could not find membership ({resp.status}): {text[:300]}"
                memberships = (await resp.json()).get("groupMemberships") or []

            if not memberships:
                return False, "That Roblox user is not in the group."

            membership_path = memberships[0].get("path") or ""
            membership_id = membership_path.split("/")[-1]
            if not membership_id:
                return False, "Could not read membership ID."

            # 3. Update the role
            patch_url = f"https://apis.roblox.com/cloud/v2/groups/{ROBLOX_GROUP_ID}/memberships/{membership_id}"
            payload = {"role": f"groups/{ROBLOX_GROUP_ID}/roles/{role_id}"}
            async with session.patch(patch_url, headers=json_headers, json=payload) as resp:
                text = await resp.text()
                if resp.status in (200, 204):
                    return True, "Rank updated successfully"
                return False, f"Roblox API error {resp.status}: {text[:400]}"

    except Exception as e:
        return False, f"Request failed: {e}"


async def update_discord_roles_for_rank(member: discord.Member, new_rank: int):
    """Remove old ranking roles and give the correct one for the new rank"""
    guild = member.guild
    bot_top = guild.me.top_role

    # All ranking Discord roles
    all_ranking_role_ids = set(ROBLOX_RANK_TO_DISCORD_ROLE.values())

    roles_to_remove = []
    for role in member.roles:
        if role.id in all_ranking_role_ids and not role.managed and role.position < bot_top.position:
            roles_to_remove.append(role)

    if roles_to_remove:
        try:
            await member.remove_roles(*roles_to_remove, reason="Rank change")
        except Exception as e:
            print(f"Failed to remove old ranking roles: {e}")

    # Add the new role
    new_role_id = ROBLOX_RANK_TO_DISCORD_ROLE.get(new_rank)
    if new_role_id:
        new_role = guild.get_role(new_role_id)
        if new_role and new_role.position < bot_top.position:
            try:
                await member.add_roles(new_role, reason="Rank change")
            except Exception as e:
                print(f"Failed to add new ranking role: {e}")


def can_use_ranking_commands(user: discord.Member) -> bool:
    if user.id in OWNER_IDS or is_admin(user):
        return True
    return any(role.id == GROUP_RANKING_PERMISSIONS_ROLE_ID for role in user.roles)

async def restore_from_backup(member: discord.Member, backup_type: str, special_role_id: int):
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

    if special_role and special_role in member.roles:
        try:
            await member.remove_roles(special_role, reason=f"Removed {backup_type}")
        except:
            pass

    roles_added = []
    if row and row[0]:
        previous_role_ids = [int(rid) for rid in row[0].split(",") if rid.strip()]
        for rid in previous_role_ids:
            role = guild.get_role(rid)
            if role and role != special_role and not role.managed and role.position < bot_top_role.position:
                roles_added.append(role)

    if ver_header and ver_header not in roles_added and ver_header.position < bot_top_role.position:
        roles_added.append(ver_header)
    if verified and verified not in roles_added and verified.position < bot_top_role.position:
        roles_added.append(verified)

    if roles_added:
        try:
            await member.add_roles(*roles_added, reason=f"Restored roles after {backup_type} removal")
        except Exception as e:
            print(f"[Main Guild Restore Error] {e}")

    await delete_role_backup(member.id, guild.id, backup_type)

    if roles_added:
        return f"✅ Disciplinary role removed and previous roles restored ({len(roles_added)} roles)."
    return "✅ Disciplinary role removed. No previous roles found in backup."

async def remove_cross_guild_roles(user_id: int):
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
            if role and role in other_member.roles and not role.managed:
                try:
                    await other_member.remove_roles(role, reason="Police Disciplinary Action (cross-guild)")
                except Exception as e:
                    print(f"[Cross-Guild] Failed to remove role {role_id}: {e}")

async def restore_cross_guild_roles(user_id: int, backup_type: str):
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
            if role and not role.managed:
                roles_to_add.append(role)

        if roles_to_add:
            try:
                await other_member.add_roles(*roles_to_add, reason=f"Restored after {backup_type}")
                await delete_role_backup(user_id, guild_id, backup_type)
            except Exception as e:
                print(f"[Cross-Guild Restore Error] {other_guild.name}: {e}")

# ================== POLICE DISCIPLINARY ==================
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
        missing = []
        if not ver_header: missing.append("Verification Header")
        if not verified: missing.append("Verified")
        if not target_role: missing.append("Target Role")
        await interaction.followup.send(f"❌ Required roles not found: {', '.join(missing)}")
        return

    keep_roles = [ver_header, verified]

    try:
        await save_role_backup(member, backup_type)

        # Safer role stripping – skips Server Booster and other managed roles
        bot_top = guild.me.top_role
        roles_to_remove = []
        for role in member.roles:
            if role in keep_roles or role == guild.default_role:
                continue
            if role.managed or role.position >= bot_top.position:
                continue
            roles_to_remove.append(role)

        if roles_to_remove:
            await member.remove_roles(*roles_to_remove, reason=f"Police {action} by {interaction.user}")

        if is_permanent:
            await member.add_roles(target_role, reason=f"Police Blacklist - {target_role.name}")
            role_text = f"{target_role.mention} (Permanent)"
        else:
            if not duration:
                await interaction.followup.send("❌ Duration is required (e.g. 7d, 28d).")
                return
            try:
                seconds = parse_duration(duration)
            except Exception:
                await interaction.followup.send("❌ Invalid duration format. Use e.g. `7d`, `14d`, `28d`.")
                return
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
        error_msg = traceback.format_exc()
        print(f"❌ FULL ERROR in police {action}:\n{error_msg}")
        await interaction.followup.send(f"❌ Something went wrong.\n```{str(e)[:1500]}```")

# ================== DURATION PARSERS ==================
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
    duration = duration.lower().strip()
    num = int(''.join(filter(str.isdigit, duration)) or 1)
    if "week" in duration:
        return num * 7
    return num

# ================== DATABASE ==================
async def setup_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS global_bans (
            user_id TEXT PRIMARY KEY,
            reason TEXT,
            timestamp INTEGER
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS temp_roles (
            user_id TEXT,
            guild_id TEXT,
            role_id TEXT,
            expires_at INTEGER,
            added_by TEXT,
            PRIMARY KEY (user_id, guild_id, role_id)
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS active_loas (
            user_id TEXT PRIMARY KEY,
            approved_by TEXT,
            start_time INTEGER,
            end_time INTEGER,
            reason TEXT,
            length TEXT
        )""")
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
        await db.execute("INSERT OR REPLACE INTO global_bans VALUES (?, ?, ?)",
                         (str(user_id), reason, int(time.time())))
        await db.commit()

async def remove_global_ban(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM global_bans WHERE user_id = ?", (str(user_id),))
        await db.commit()

async def is_banned(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT 1 FROM global_bans WHERE user_id = ?", (str(user_id),)) as cursor:
            return await cursor.fetchone() is not None

async def add_temp_role(user_id: int, guild_id: int, role_id: int, expires_at: int, added_by: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""INSERT OR REPLACE INTO temp_roles 
            (user_id, guild_id, role_id, expires_at, added_by)
            VALUES (?, ?, ?, ?, ?)""",
            (str(user_id), str(guild_id), str(role_id), expires_at, str(added_by)))
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
        async with db.execute(
            "SELECT user_id, guild_id, role_id FROM temp_roles WHERE expires_at <= ?", (now,)
        ) as cursor:
            expired = await cursor.fetchall()
        for user_id, guild_id, role_id in expired:
            try:
                guild = bot.get_guild(int(guild_id))
                if guild:
                    member = guild.get_member(int(user_id))
                    role = guild.get_role(int(role_id))
                    if member and role:
                        await member.remove_roles(role, reason="Temp role expired")
            except:
                pass
        await db.execute("DELETE FROM temp_roles WHERE expires_at <= ?", (now,))
        await db.commit()

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
        await db.execute("DELETE FROM active_loas WHERE end_time <= ?", (now,))
        await db.commit()

# ================== BOT ==================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

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
                await guild.ban(self.target_user, reason=f"Global Ban: {self.reason}")
                success += 1
            except:
                pass
        await add_global_ban(self.target_user.id, self.reason)
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.add_field(name="✅ Accepted By", value=f"{interaction.user.mention}", inline=False)
        embed.add_field(name="Banned In", value=f"{success} servers", inline=True)
        self.clear_items()
        self.add_item(discord.ui.Button(label=f"Accepted by {interaction.user.display_name}", style=discord.ButtonStyle.green, disabled=True))
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
        self.clear_items()
        self.add_item(discord.ui.Button(label=f"Denied by {interaction.user.display_name}", style=discord.ButtonStyle.red, disabled=True))
        await interaction.message.edit(embed=embed, view=self)

class LOARequestView(discord.ui.View):
    def __init__(self, requester: discord.Member = None, reason: str = None, length: str = None):
        super().__init__(timeout=None)
        self.requester = requester
        self.reason = reason
        self.length = length

    def can_manage_loa(self, user: discord.Member) -> bool:
        if user.id in OWNER_IDS or any(role.id in ADMIN_ROLE_IDS for role in user.roles):
            return True
        return any(role.id == LOA_TRACKER_ROLE_ID for role in user.roles)

    async def get_loa_data(self, interaction: discord.Interaction):
        if self.requester and self.reason and self.length:
            return self.requester, self.reason, self.length
        embed = interaction.message.embeds[0]
        requester_mention = embed.fields[0].value
        length = embed.fields[1].value
        reason = embed.fields[2].value
        requester_id = int(''.join(filter(str.isdigit, requester_mention)))
        requester = interaction.guild.get_member(requester_id) or await interaction.guild.fetch_member(requester_id)
        return requester, reason, length

    @discord.ui.button(label="Approve LOA", style=discord.ButtonStyle.green, custom_id="loa_approve")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.can_manage_loa(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to approve LOAs.", ephemeral=True)
            return
        await interaction.response.defer()
        requester, reason, length = await self.get_loa_data(interaction)
        guild = interaction.guild
        member = guild.get_member(requester.id)
        loa_role = guild.get_role(LOA_ROLE_ID)
        days = parse_loa_duration(length)
        end_time = int(time.time()) + (days * 86400)
        if member and loa_role:
            try:
                await member.add_roles(loa_role, reason=f"LOA Approved • {length}")
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("""INSERT OR REPLACE INTO active_loas 
                        (user_id, approved_by, start_time, end_time, reason, length)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                        (str(requester.id), str(interaction.user.id), int(time.time()), end_time, reason, length))
                    await db.commit()
                await add_temp_role(requester.id, guild.id, LOA_ROLE_ID, end_time, interaction.user.id)
            except Exception as e:
                print(f"LOA approve error: {e}")
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.set_field_at(3, name="Status", value=f"Approved by {interaction.user.mention}", inline=False)
        embed.set_footer(text="UKRP LOA Request - Approved")
        self.clear_items()
        self.add_item(discord.ui.Button(label=f"LOA Approved by {interaction.user.display_name}", style=discord.ButtonStyle.green, disabled=True))
        await interaction.message.edit(embed=embed, view=self)
        log_channel = bot.get_channel(LOA_LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(title="UKRP LOA Request Log", color=discord.Color.green(),
                                      description=f"{requester.mention}'s LOA request has been accepted by {interaction.user.mention}")
            log_embed.add_field(name="Duration", value=length, inline=False)
            log_embed.add_field(name="Reason", value=reason, inline=False)
            await log_channel.send(embed=log_embed)

    @discord.ui.button(label="Deny LOA", style=discord.ButtonStyle.red, custom_id="loa_deny")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.can_manage_loa(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to deny LOAs.", ephemeral=True)
            return
        await interaction.response.defer()
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.set_field_at(3, name="Status", value=f"Denied by {interaction.user.mention}", inline=False)
        embed.set_footer(text="UKRP LOA Request - Denied")
        self.clear_items()
        self.add_item(discord.ui.Button(label=f"LOA Denied by {interaction.user.display_name}", style=discord.ButtonStyle.red, disabled=True))
        await interaction.message.edit(embed=embed, view=self)

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
            description = (
                f"A training for the Response Division will be held at {self.time}. Please make sure you are in-game, on the Police team in your uniform and sat down in the briefing room.\n\n"
                f"If you can no longer attend the training, please press the \"Attending\" button again."
            )
            vc_field_name = "Response Training VC"
            vc_link = f"https://discord.com/channels/1457118167078801631/{RESPONSE_TRAINING_VC_ID}"
        else:
            title = f"Roads Training — {self.status}"
            description = (
                f"A training for the Roads Policing Unit will be held at {self.time}. Please make sure you are in-game, on the Police team in your uniform and sat down in the briefing room.\n\n"
                f"If you can no longer attend the training, please press the \"Attending\" button again."
            )
            vc_field_name = "Roads Training VC"
            vc_link = f"https://discord.com/channels/1457118167078801631/{ROADS_TRAINING_VC_ID}"

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
        embed.add_field(name="────────────", value="\u200b", inline=False)
        if self.attendees:
            embed.add_field(name="Attendees", value="\n".join([a.mention for a in self.attendees]), inline=False)
        else:
            embed.add_field(name="Attendees", value="No one yet", inline=False)
        embed.add_field(name="────────────", value="\u200b", inline=False)
        embed.add_field(name=vc_field_name, value=vc_link, inline=False)
        if self.ended_by:
            embed.add_field(name="Ended By", value=self.ended_by.mention, inline=False)
        return embed

    def disable_attendance_buttons(self):
        for child in self.children:
            if child.label in ["Attend as Co-Host", "Attending"]:
                child.disabled = True

    @discord.ui.button(label="Start", style=discord.ButtonStyle.green, emoji="▶️")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        allowed_role = ENTRY_PROGRAMME_INSTRUCTOR_ROLE_ID if self.division == "Response" else ROADS_INSTRUCTOR_ROLE_ID
        if not any(r.id == allowed_role for r in interaction.user.roles):
            await interaction.response.send_message("❌ Only the correct Instructor role can start this training.", ephemeral=True)
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
        if interaction.user == self.host:
            await interaction.response.send_message("❌ You are already hosting the training.", ephemeral=True)
            return
        if interaction.user in self.co_hosts:
            self.co_hosts.remove(interaction.user)
            await interaction.message.edit(embed=self.create_embed(), view=self)
            await interaction.response.send_message("You have withdrawn from Co-Host.", ephemeral=True)
        else:
            if len(self.co_hosts) >= 3:
                await interaction.response.send_message("❌ Maximum of 3 Co-Hosts allowed.", ephemeral=True)
                return
            self.co_hosts.append(interaction.user)
            await interaction.message.edit(embed=self.create_embed(), view=self)
            await interaction.response.send_message("You are now a Co-Host!", ephemeral=True)

    @discord.ui.button(label="Attending", style=discord.ButtonStyle.green, emoji="✅")
    async def attending_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.status != "Upcoming":
            await interaction.response.send_message("❌ You can no longer mark yourself as attending.", ephemeral=True)
            return
        allowed_role = RESPONSE_TRAINEE_ROLE_ID if self.division == "Response" else ROADS_TRAINEE_ROLE_ID
        if not any(r.id == allowed_role for r in interaction.user.roles):
            await interaction.response.send_message("❌ Only the correct Trainee role can mark themselves as attending.", ephemeral=True)
            return
        if interaction.user in self.attendees:
            self.attendees.remove(interaction.user)
            await interaction.message.edit(embed=self.create_embed(), view=self)
            await interaction.response.send_message("You have withdrawn from attending.", ephemeral=True)
        else:
            self.attendees.append(interaction.user)
            await interaction.message.edit(embed=self.create_embed(), view=self)
            await interaction.response.send_message("You are now marked as attending!", ephemeral=True)

    @discord.ui.button(label="End Training", style=discord.ButtonStyle.red, emoji="🛑")
    async def end_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        allowed_role = ENTRY_PROGRAMME_INSTRUCTOR_ROLE_ID if self.division == "Response" else ROADS_INSTRUCTOR_ROLE_ID
        if not any(r.id == allowed_role for r in interaction.user.roles):
            await interaction.response.send_message("❌ Only the correct Instructor role can end this training.", ephemeral=True)
            return
        if self.status == "Ended":
            await interaction.response.send_message("❌ Training has already ended.", ephemeral=True)
            return
        self.status = "Ended"
        self.ended_by = interaction.user
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(embed=self.create_embed(), view=self)
        await interaction.response.send_message("Training has ended.", ephemeral=True)

# ================== EVENTS ==================
@bot.event
async def on_ready():
    await setup_db()
    bot.loop.create_task(temp_role_cleanup_loop())
    bot.loop.create_task(loa_cleanup_loop())
    bot.add_view(LOARequestView())
    print("✅ LOA Request View registered as persistent")
    await bot.tree.sync()
    print("✅ Slash commands synced globally")
    print(f"✅ Logged in as {bot.user}")

async def temp_role_cleanup_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        await remove_expired_temp_roles()
        await asyncio.sleep(60)

async def loa_cleanup_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        await remove_expired_loas()
        await asyncio.sleep(300)

# ================== COMMANDS ==================
@bot.tree.command(name="policeblacklist", description="Blacklist a user (strip roles + permanent Police Barred List)")
@app_commands.describe(user="Target user")
async def policeblacklist(interaction: discord.Interaction, user: discord.Member):
    await apply_police_disciplinary(interaction, user, "blacklist")

@bot.tree.command(name="policeremoval", description="Apply police removal (strip roles + temporary Removal Cooldown)")
@app_commands.describe(user="Target user", duration="Duration (e.g. 28d)")
async def policeremoval(interaction: discord.Interaction, user: discord.Member, duration: str):
    await apply_police_disciplinary(interaction, user, "removal", duration)

@bot.tree.command(name="removeblacklist", description="Remove Police Barred List role and restore previous roles")
@app_commands.describe(user="Target user")
async def removeblacklist(interaction: discord.Interaction, user: discord.Member):
    if not can_use_police_commands(interaction.user):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    main_result = await restore_from_backup(user, "blacklist", POLICE_BARRED_LIST_ROLE_ID)
    await restore_cross_guild_roles(user.id, "blacklist")
    embed = discord.Embed(title="Police Blacklist Removed", color=discord.Color.green())
    embed.add_field(name="Target User", value=f"{user.mention} (`{user.id}`)", inline=False)
    embed.add_field(name="Result", value=main_result, inline=False)
    embed.set_footer(text=f"Action by {interaction.user.display_name}")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="removepoliceremoval", description="Remove Removal Cooldown role and restore previous roles")
@app_commands.describe(user="Target user")
async def removepoliceremoval(interaction: discord.Interaction, user: discord.Member):
    if not can_use_police_commands(interaction.user):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    main_result = await restore_from_backup(user, "removal", REMOVAL_COOLDOWN_ROLE_ID)
    await restore_cross_guild_roles(user.id, "removal")
    embed = discord.Embed(title="Police Removal Reversed", color=discord.Color.green())
    embed.add_field(name="Target User", value=f"{user.mention} (`{user.id}`)", inline=False)
    embed.add_field(name="Result", value=main_result, inline=False)
    embed.set_footer(text=f"Action by {interaction.user.display_name}")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="loarequest", description="Submit a Leave of Absence request")
@app_commands.describe(reason="Reason for LOA", length="Length of LOA (e.g. 1 week, 2 weeks, 10 days)")
async def loarequest(interaction: discord.Interaction, reason: str, length: str):
    member = interaction.guild.get_member(interaction.user.id)
    if member:
        if any(role.id == INACTIVITY_WARNING_ROLE_ID for role in member.roles):
            await interaction.response.send_message("❌ You cannot request LOA while having an Inactivity Warning.", ephemeral=True)
            return
        if any(role.id == LOA_COOLDOWN_ROLE_ID for role in member.roles):
            await interaction.response.send_message("❌ You are currently on LOA Cooldown.", ephemeral=True)
            return
    if not has_request_role(interaction.user) and not is_admin(interaction.user):
        await interaction.response.send_message("❌ You cannot request LOAs", ephemeral=True)
        return
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
    if not (is_admin(interaction.user) or any(role.id == LOA_TRACKER_ROLE_ID for role in interaction.user.roles)):
        await interaction.response.send_message("❌ Only LOA Trackers can view active LOAs.", ephemeral=True)
        return
    await interaction.response.defer()
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id, approved_by, end_time FROM active_loas ORDER BY end_time") as cursor:
            active_loas = await cursor.fetchall()
    if not active_loas:
        return await interaction.followup.send("✅ No users are currently on LOA.")
    embed = discord.Embed(title="Current Active LOAs", color=discord.Color.blue())
    for user_id, approved_by, end_time in active_loas:
        member = interaction.guild.get_member(int(user_id))
        if not member:
            continue
        end_dt = datetime.fromtimestamp(end_time, tz=timezone.utc)
        time_left = discord.utils.format_dt(end_dt, style='R')
        embed.add_field(name=member.display_name, value=f"**Approved by:** <@{approved_by}>\n**Ends:** {time_left}", inline=False)
    embed.set_footer(text=f"Total on LOA: {len(active_loas)}")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="role", description="Add or remove a role from a user")
@app_commands.describe(action="add or remove", user="The user to modify", role="The role to add or remove", reason="Reason (required when adding to yourself)")
@app_commands.choices(action=[app_commands.Choice(name="Add", value="add"), app_commands.Choice(name="Remove", value="remove")])
async def role(interaction: discord.Interaction, action: str, user: discord.Member, role: discord.Role, reason: str = None):
    if not can_manage_roles(interaction.user, interaction.guild):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return
    action = action.lower()
    if action == "add" and user.id == interaction.user.id and not reason:
        await interaction.response.send_message("❌ You must provide a reason when adding a role to yourself.", ephemeral=True)
        return
    if role.position >= interaction.user.top_role.position and interaction.user.id not in OWNER_IDS:
        await interaction.response.send_message(f"❌ You cannot manage {role.mention} because it is higher than or equal to your highest role.", ephemeral=True)
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

@bot.tree.command(name="temprole", description="Add or remove temporary roles")
@app_commands.describe(action="add or remove", user="Target user", role="Role to add/remove", duration="Duration (e.g. 1h, 30m, 7d) - only for add")
@app_commands.choices(action=[app_commands.Choice(name="Add", value="add"), app_commands.Choice(name="Remove", value="remove")])
async def temprole(interaction: discord.Interaction, action: str, user: discord.User, role: discord.Role, duration: str = None):
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

@bot.tree.command(name="training", description="Schedule a training session")
@app_commands.describe(division="Which division is the training for?", time="When is the training? (e.g. Tonight at 8pm)")
@app_commands.choices(division=[
    app_commands.Choice(name="Response Division", value="Response"),
    app_commands.Choice(name="Roads Policing Unit", value="Roads")
])
async def training(interaction: discord.Interaction, division: str, time: str):
    try:
        if not any(r.id in [ENTRY_PROGRAMME_INSTRUCTOR_ROLE_ID, ROADS_INSTRUCTOR_ROLE_ID] for r in interaction.user.roles):
            await interaction.response.send_message("❌ Only Entry Programme Instructors and Roads Instructors can use this command.", ephemeral=True)
            return
        view = TrainingView(division, time, interaction.user)
        embed = view.create_embed()
        if division == "Response":
            ping = f"<@&{ENTRY_PROGRAMME_INSTRUCTOR_ROLE_ID}> <@&{RESPONSE_TRAINEE_ROLE_ID}>"
        else:
            ping = f"<@&{ROADS_INSTRUCTOR_ROLE_ID}> <@&{ROADS_TRAINEE_ROLE_ID}>"
        channel = bot.get_channel(TRAINING_ANNOUNCEMENTS_CHANNEL_ID)
        if channel is None:
            await interaction.response.send_message("❌ Could not find the training announcements channel.", ephemeral=True)
            return
        await channel.send(content=ping, embed=embed, view=view)
        await interaction.response.send_message("Training announcement has been posted!", ephemeral=True)
    except Exception as error:
        print(f"❌ ERROR in /training command: {error}")
        await interaction.response.send_message("❌ Something went wrong. Check the bot logs.", ephemeral=True)

@bot.tree.command(name="logtraining", description="Log a completed training session")
@app_commands.describe(training_type="Type of training", hosts="Mention the host(s)", attendees="Mention the attendees", proof="Upload a screenshot as proof")
async def logtraining(interaction: discord.Interaction, training_type: str, hosts: str, attendees: str, proof: discord.Attachment):
    if interaction.channel.id != TRAINING_LOGS_CHANNEL_ID:
        await interaction.response.send_message("❌ This command can only be used in the Training Logs channel.", ephemeral=True)
        return
    if not any(r.id in [ENTRY_PROGRAMME_INSTRUCTOR_ROLE_ID, ROADS_INSTRUCTOR_ROLE_ID] for r in interaction.user.roles):
        await interaction.response.send_message("❌ Only Entry Programme Instructors and Roads Instructors can use this command.", ephemeral=True)
        return
    embed = discord.Embed(title="Training Log", color=discord.Color.blue())
    embed.add_field(name="Submitted By", value=interaction.user.mention, inline=False)
    embed.add_field(name="Type of Training", value=training_type, inline=False)
    embed.add_field(name="Hosts", value=hosts, inline=False)
    embed.add_field(name="Attendees", value=attendees, inline=False)
    embed.add_field(name="Proof", value="\u200b", inline=False)
    embed.set_image(url=proof.url)
    embed.set_footer(text=f"Logged by {interaction.user.display_name}")
    channel = bot.get_channel(TRAINING_LOGS_CHANNEL_ID)
    await channel.send(embed=embed)
    await interaction.response.send_message("✅ Training log has been submitted.", ephemeral=True)

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
                await guild.ban(user, reason=f"Global Ban: {reason}")
                success += 1
            except:
                pass
    except Exception as e:
        print(f"❌ Error during globalban: {e}")
    await interaction.followup.send(f"✅ Banned in {success} guilds")

@bot.tree.command(name="unglobalban", description="Unban a user globally")
async def unglobalban(interaction: discord.Interaction, user: discord.User):
    if interaction.user.id not in OWNER_IDS and not is_admin(interaction.user):
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
@app_commands.describe(user="User to request ban for", reason="Reason")
async def globalbanrequest(interaction: discord.Interaction, user: discord.User, reason: str):
    if not any(role.id in GLOBALBAN_REQUEST_ROLE_IDS for role in interaction.user.roles) and not is_admin(interaction.user):
        await interaction.response.send_message("❌ Not allowed", ephemeral=True)
        return
    embed = discord.Embed(title="Global Ban Request", color=discord.Color.orange())
    embed.add_field(name="Target", value=f"{user.mention} (`{user.id}`)", inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Requested By", value=interaction.user.mention, inline=False)
    view = GlobalBanRequestView(user, reason, interaction.user)
    await interaction.response.send_message(embed=embed, view=view)

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

@bot.tree.command(name="setrank", description="Set a user's rank in the Roblox group")
@app_commands.describe(
    user="Discord user to rank",
    rank="Rank name",
    roblox_username="Optional Roblox username if Bloxlink cannot find them"
)
@app_commands.choices(rank=[
    app_commands.Choice(name=name, value=str(num))
    for num, name in ROBLOX_RANK_NAMES.items()
])
async def setrank(
    interaction: discord.Interaction,
    user: discord.Member,
    rank: str,
    roblox_username: str = None
):
    if not can_use_ranking_commands(interaction.user):
        await interaction.response.send_message("❌ You don't have permission to use ranking commands.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    rank_number = int(rank)
    rank_name = ROBLOX_RANK_NAMES.get(rank_number, "Unknown")

    roblox_id, source = await resolve_roblox_id(user, roblox_username)
    if not roblox_id:
        await interaction.followup.send(f"❌ {source}")
        return

    success, message = await set_roblox_rank(roblox_id, rank_number)
    if not success:
        await interaction.followup.send(f"❌ Failed to set rank in Roblox group.\n`{message}`")
        return

    await update_discord_roles_for_rank(user, rank_number)

    embed = discord.Embed(title="Rank Updated", color=discord.Color.green())
    embed.add_field(name="User", value=user.mention, inline=False)
    embed.add_field(name="New Rank", value=rank_name, inline=True)
    embed.add_field(name="Rank Number", value=str(rank_number), inline=True)
    embed.add_field(name="Roblox ID", value=str(roblox_id), inline=True)
    embed.add_field(name="Lookup", value=source, inline=True)
    embed.set_footer(text=f"Action by {interaction.user.display_name}")
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="promote", description="Promote a user one rank in the Roblox group")
@app_commands.describe(
    user="Discord user to promote",
    roblox_username="Optional Roblox username if Bloxlink cannot find them"
)
async def promote(
    interaction: discord.Interaction,
    user: discord.Member,
    roblox_username: str = None
):
    if not can_use_ranking_commands(interaction.user):
        await interaction.response.send_message("❌ You don't have permission to use ranking commands.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    current_rank = None
    for rank_num, role_id in ROBLOX_RANK_TO_DISCORD_ROLE.items():
        if any(r.id == role_id for r in user.roles):
            current_rank = rank_num
            break

    if current_rank is None:
        current_rank = SORTED_RANKS[0]

    try:
        idx = SORTED_RANKS.index(current_rank)
        if idx >= len(SORTED_RANKS) - 1:
            await interaction.followup.send(f"❌ {user.mention} is already at the highest rank.")
            return
        new_rank = SORTED_RANKS[idx + 1]
    except ValueError:
        new_rank = SORTED_RANKS[0]

    roblox_id, source = await resolve_roblox_id(user, roblox_username)
    if not roblox_id:
        await interaction.followup.send(f"❌ {source}")
        return

    success, message = await set_roblox_rank(roblox_id, new_rank)
    if not success:
        await interaction.followup.send(f"❌ Failed to promote in Roblox group.\n`{message}`")
        return

    await update_discord_roles_for_rank(user, new_rank)

    old_name = ROBLOX_RANK_NAMES.get(current_rank, "Unknown")
    new_name = ROBLOX_RANK_NAMES.get(new_rank, "Unknown")
    display_name = roblox_username or user.display_name
    who = f"{display_name} ({roblox_id})" if roblox_id else display_name

    embed = discord.Embed(
        title="Promotion",
        description=f"The role of **{who}** was changed from **{old_name}** to **{new_name}**.",
        color=discord.Color.green()
    )
    avatar_url = await get_roblox_avatar(roblox_id)
    if avatar_url:
        embed.set_thumbnail(url=avatar_url)
    embed.set_footer(text=f"Action by {interaction.user.display_name}")
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="demote", description="Demote a user one rank in the Roblox group")
@app_commands.describe(
    user="Discord user to demote",
    roblox_username="Optional Roblox username if Bloxlink cannot find them"
)
async def demote(
    interaction: discord.Interaction,
    user: discord.Member,
    roblox_username: str = None
):
    if not can_use_ranking_commands(interaction.user):
        await interaction.response.send_message("❌ You don't have permission to use ranking commands.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    current_rank = None
    for rank_num, role_id in ROBLOX_RANK_TO_DISCORD_ROLE.items():
        if any(r.id == role_id for r in user.roles):
            current_rank = rank_num
            break

    if current_rank is None:
        await interaction.followup.send(f"❌ {user.mention} has no ranking role to demote from.")
        return

    try:
        idx = SORTED_RANKS.index(current_rank)
        if idx <= 0:
            await interaction.followup.send(f"❌ {user.mention} is already at the lowest rank.")
            return
        new_rank = SORTED_RANKS[idx - 1]
    except ValueError:
        await interaction.followup.send("❌ Could not determine current rank.")
        return

    roblox_id, source = await resolve_roblox_id(user, roblox_username)
    if not roblox_id:
        await interaction.followup.send(f"❌ {source}")
        return

    success, message = await set_roblox_rank(roblox_id, new_rank)
    if not success:
        await interaction.followup.send(f"❌ Failed to demote in Roblox group.\n`{message}`")
        return

    await update_discord_roles_for_rank(user, new_rank)

    old_name = ROBLOX_RANK_NAMES.get(current_rank, "Unknown")
    new_name = ROBLOX_RANK_NAMES.get(new_rank, "Unknown")
    display_name = roblox_username or user.display_name
    who = f"{display_name} ({roblox_id})" if roblox_id else display_name

    embed = discord.Embed(
        title="Demotion",
        description=f"The role of **{who}** was changed from **{old_name}** to **{new_name}**.",
        color=discord.Color.red()
    )
    if roblox_id:
        avatar_url = await get_roblox_avatar(roblox_id)
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)
    embed.set_footer(text=f"Action by {interaction.user.display_name}")
    await interaction.followup.send(embed=embed)


# ================== RUN ==================
bot.run(TOKEN)