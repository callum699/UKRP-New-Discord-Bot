import discord
from discord.ext import commands
from discord import app_commands

import aiosqlite
import time
import os
from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise ValueError("❌ DISCORD_TOKEN not found")


# ✅ Your IDs (already filled)
OWNER_ID = 738790396511125654
GUILD_ID = 1457118167078801631

REQUEST_ROLE_IDS = [
    1460998934842441809 , 1457118167204630725  # roles that can REQUEST bans
]

ADMIN_ROLE_IDS = [
    1457118167204630728,  # replace with your real role ID
]

def has_request_role(user):
    return any(role.id in REQUEST_ROLE_IDS for role in user.roles)

def is_admin(user):
    if user.id == OWNER_ID:
        return True
    return any(role.id in ADMIN_ROLE_IDS for role in user.roles)

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

        # ✅ Disable buttons
        await self.disable_buttons()

        # ✅ Update embed
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()

        embed.add_field(
            name="✅ Accepted By",
            value=f"{interaction.user} (`{interaction.user.id}`)",
            inline=False
        )

        embed.timestamp = discord.utils.utcnow()

        # ✅ Edit message (this replaces buttons)
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="❌ Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ Not allowed", ephemeral=True)
            return

        # ✅ Disable buttons
        await self.disable_buttons()

        # ✅ Update embed
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.greyple()

        embed.add_field(
            name="❌ Denied By",
            value=f"{interaction.user} (`{interaction.user.id}`)",
            inline=False
        )

        embed.timestamp = discord.utils.utcnow()

        # ✅ Edit message
        await interaction.response.edit_message(embed=embed, view=self)


LOG_CHANNEL_ID = 1504537214829461677  # 🔁 replace with your channel ID

DB_NAME = "globalbans.db"

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ✅ Database setup
async def setup_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS global_bans (
            user_id TEXT PRIMARY KEY,
            reason TEXT,
            banned_at INTEGER
        )
        """)
        await db.commit()

async def add_global_ban(user_id, reason):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR REPLACE INTO global_bans VALUES (?, ?, ?)",
            (str(user_id), reason, int(time.time()))
        )
        await db.commit()

async def remove_global_ban(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "DELETE FROM global_bans WHERE user_id = ?",
            (str(user_id),)
        )
        await db.commit()

async def is_banned(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT 1 FROM global_bans WHERE user_id = ?",
            (str(user_id),)
        ) as cursor:
            return await cursor.fetchone() is not None

async def get_all_bans():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM global_bans") as cursor:
            return await cursor.fetchall()
        
async def log_action(embed):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        try:
            await channel.send(embed=embed)
        except:
            print("❌ Failed to send log")

@bot.event
async def on_ready():
    await setup_db()

    guild = discord.Object(id=GUILD_ID)

    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)

    print(f"✅ Logged in as {bot.user}")


@bot.tree.command(name="globalban", description="Ban a user from all guilds")
@app_commands.describe(user="User to ban", reason="Reason for ban")
async def globalban(interaction: discord.Interaction, user: discord.User, reason: str = "No reason provided"):

    # ✅ Permission check
    if interaction.user.id != OWNER_ID:
        user_roles = [role.id for role in interaction.user.roles]

        if not any(role_id in ADMIN_ROLE_IDS for role_id in user_roles):
            await interaction.response.send_message("❌ Not allowed", ephemeral=True)
            return

    await interaction.response.defer()

    success = 0

    try:
        # ✅ Save to DB
        await add_global_ban(user.id, reason)

        # ✅ Ban loop
        for guild in bot.guilds:
            try:
                await guild.ban(user, reason=reason)
                success += 1
            except:
                pass

    except Exception as e:
        print(f"❌ Error during globalban: {e}")

    # ✅ ALWAYS send response
    await interaction.followup.send(f"✅ Banned in {success} guilds")

    # ✅ ALWAYS log (outside try block)
    try:
        embed = discord.Embed(
            title="🔴 Global Ban",
            color=discord.Color.red()
        )

        embed.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
        embed.add_field(name="Banned By", value=f"{interaction.user} (`{interaction.user.id}`)", inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Guilds Affected", value=str(success), inline=False)
        embed.timestamp = discord.utils.utcnow()

        await log_action(embed)

    except Exception as e:
        print(f"❌ Logging failed: {e}")

@bot.tree.command(name="unglobalban", description="Unban a user globally")
async def unglobalban(interaction: discord.Interaction, user: discord.User):

    # ✅ Permission check
    if interaction.user.id != OWNER_ID:
        user_roles = [role.id for role in interaction.user.roles]

        if not any(role_id in ADMIN_ROLE_IDS for role_id in user_roles):
            await interaction.response.send_message("❌ Not allowed", ephemeral=True)
            return

    # ✅ ALWAYS defer immediately (MOST IMPORTANT LINE)
    await interaction.response.defer()

    success = 0

    try:
        # ✅ Remove from database
        await remove_global_ban(user.id)

        # ✅ Unban from servers
        for guild in bot.guilds:
            try:
                await guild.unban(user)
                success += 1
            except:
                pass

    except Exception as e:
        print(f"❌ Error during unglobalban: {e}")

    # ✅ Send response AFTER work is done
    await interaction.followup.send(f"✅ Unbanned in {success} guilds")

    # ✅ Logging
    try:
        embed = discord.Embed(
            title="🟢 Global Unban",
            color=discord.Color.green()
        )

        embed.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
        embed.add_field(name="Unbanned By", value=f"{interaction.user} (`{interaction.user.id}`)", inline=False)
        embed.add_field(name="Guilds Affected", value=str(success), inline=False)
        embed.add_field(name="Reason", value="Manual unban", inline=False)

        embed.timestamp = discord.utils.utcnow()

        await log_action(embed)

    except Exception as e:
        print(f"❌ Logging failed: {e}")


@bot.tree.command(name="globalbanrequest", description="Request a global ban")
@app_commands.describe(user="User to ban", reason="Reason")
async def globalbanrequest(interaction: discord.Interaction, user: discord.User, reason: str):

    # ✅ Check request role
    if not has_request_role(interaction.user) and interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ You cannot request bans", ephemeral=True)
        return

    # ✅ Send instant response (NO defer)
    await interaction.response.send_message("✅ Request sent", ephemeral=True)

    # ✅ Create embed
    embed = discord.Embed(
        title="📩 Global Ban Request",
        color=discord.Color.orange()
    )

    embed.add_field(name="Target User", value=f"{user} (`{user.id}`)", inline=False)
    embed.add_field(name="Requested By", value=f"{interaction.user} (`{interaction.user.id}`)", inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)

    embed.timestamp = discord.utils.utcnow()

    # ✅ Get channel safely
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(LOG_CHANNEL_ID)
        except Exception as e:
            print(f"❌ Failed to get channel: {e}")
            return

    # ✅ Buttons
    view = GlobalBanRequestView(user, reason, interaction.user)

    # ✅ Send request message
    await channel.send(embed=embed, view=view)


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

bot.run(TOKEN)
