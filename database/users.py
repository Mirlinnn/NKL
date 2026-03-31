import logging
from typing import Optional, Tuple
from .core import execute, fetchone, fetchall, get_connection

logger = logging.getLogger(__name__)

async def create_users_table(conn):
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            banned INTEGER DEFAULT 0,
            accepted_terms INTEGER DEFAULT 0,
            balance REAL DEFAULT 0,
            banned_by INTEGER,
            banned_at TIMESTAMP,
            ban_reason TEXT
        )
    ''')
    for col in ['balance', 'accepted_terms']:
        try:
            await conn.execute(f'SELECT {col} FROM users LIMIT 1')
        except:
            await conn.execute(f'ALTER TABLE users ADD COLUMN {col} {"REAL DEFAULT 0" if col == "balance" else "INTEGER DEFAULT 0"}')
    for col in ['banned_by', 'banned_at', 'ban_reason']:
        try:
            await conn.execute(f'SELECT {col} FROM users LIMIT 1')
        except:
            await conn.execute(f'ALTER TABLE users ADD COLUMN {col} TEXT')
    logger.info("Table 'users' ready")

async def add_user(user_id: int):
    await execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))

async def get_balance(user_id: int) -> float:
    row = await fetchone('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    return row[0] if row else 0.0

async def update_balance(user_id: int, amount: float):
    await execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))

async def set_balance(user_id: int, amount: float):
    await execute('UPDATE users SET balance = ? WHERE user_id = ?', (amount, user_id))

async def is_banned(user_id: int) -> bool:
    row = await fetchone('SELECT banned FROM users WHERE user_id = ?', (user_id,))
    return row and row[0] == 1

async def get_ban_info(user_id: int) -> Optional[Tuple]:
    return await fetchone('SELECT banned, banned_by, banned_at, ban_reason FROM users WHERE user_id = ?', (user_id,))

async def ban_user(user_id: int, admin_id: int, reason: str = None):
    await execute(
        'UPDATE users SET banned = 1, banned_by = ?, banned_at = datetime("now"), ban_reason = ? WHERE user_id = ?',
        (admin_id, reason, user_id)
    )

async def unban_user(user_id: int):
    await execute('UPDATE users SET banned = 0, banned_by = NULL, banned_at = NULL, ban_reason = NULL WHERE user_id = ?', (user_id,))

async def has_accepted_terms(user_id: int) -> bool:
    row = await fetchone('SELECT accepted_terms FROM users WHERE user_id = ?', (user_id,))
    return row and row[0] == 1

async def accept_terms(user_id: int):
    await execute('UPDATE users SET accepted_terms = 1 WHERE user_id = ?', (user_id,))

async def get_all_users() -> list[int]:
    rows = await fetchall('SELECT user_id FROM users')
    return [row[0] for row in rows]