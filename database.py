import aiosqlite

DB_NAME = "globalbans.db"

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
