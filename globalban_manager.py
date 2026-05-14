import aiosqlite
from database import DB_NAME
import time

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