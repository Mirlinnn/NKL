import logging
from .core import execute, fetchone, fetchall

logger = logging.getLogger(__name__)

async def create_bot_state_table(conn):
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS bot_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    await conn.execute('INSERT OR IGNORE INTO bot_state (key, value) VALUES ("active", "1")')
    await conn.execute('INSERT OR IGNORE INTO bot_state (key, value) VALUES ("reason", "")')
    logger.info("Table 'bot_state' ready")

async def is_bot_active() -> bool:
    row = await fetchone('SELECT value FROM bot_state WHERE key = "active"')
    return row and row[0] == "1"

async def get_bot_status() -> dict:
    rows = await fetchall('SELECT key, value FROM bot_state')
    return {row[0]: row[1] for row in rows}

async def set_bot_active(active: bool, reason: str = ""):
    await execute('UPDATE bot_state SET value = ? WHERE key = "active"', ("1" if active else "0",))
    await execute('UPDATE bot_state SET value = ? WHERE key = "reason"', (reason,))

async def get_bot_reason() -> str:
    row = await fetchone('SELECT value FROM bot_state WHERE key = "reason"')
    return row[0] if row else ""