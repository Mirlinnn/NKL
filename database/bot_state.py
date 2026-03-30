import logging
from .core import execute, fetchone, fetchall

logger = logging.getLogger(__name__)

async def create_bot_state_table(conn):
    """Создаёт таблицу bot_state."""
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS bot_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    # Добавляем значения по ум�олчанию, если их нет
    await conn.execute('INSERT OR IGNORE INTO bot_state (key, value) VALUES ("active", "1")')
    await conn.execute('INSERT OR IGNORE INTO bot_state (key, value) VALUES ("reason", "")')
    logger.info("Table 'bot_state' ready")

async def is_bot_active() -> bool:
    """Возвращает True, если бот активен для обычных пользователей."""
    row = await fetchone('SELECT value FROM bot_state WHERE key = "active"')
    return row and row[0] == "1"

async def get_bot_status() -> dict:
    """Возвращает словарь со статусом и причиной."""
    rows = await fetchall('SELECT key, value FROM bot_state')
    return {row[0]: row[1] for row in rows}

async def set_bot_active(active: bool, reason: str = ""):
    """Устанавливает статус активности бота и причину."""
    await execute('UPDATE bot_state SET value = ? WHERE key = "active"', ("1" if active else "0",))
    await execute('UPDATE bot_state SET value = ? WHERE key = "reason"', (reason,))

async def get_bot_reason() -> str:
    """Возвращает причину, по которой бот остановлен."""
    row = await fetchone('SELECT value FROM bot_state WHERE key = "reason"')
    return row[0] if row else ""