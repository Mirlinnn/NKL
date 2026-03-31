import logging
from .core import DB_PATH, execute, fetchone, fetchall
import aiosqlite

logger = logging.getLogger(__name__)

async def create_settings_table(conn):
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    defaults = {
        "min_topup_yookassa": "1.0",
        "min_topup_heleket": "5.0",
        "default_price": "1.0",
        "currency": "RUB"
    }
    for key, value in defaults.items():
        await conn.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))
    logger.info("Table 'settings' ready")

async def get_setting(key: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT value FROM settings WHERE key = ?', (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
        await db.commit()

async def get_all_settings():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT key, value FROM settings') as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}