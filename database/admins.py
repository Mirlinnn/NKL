import logging
from typing import List
from .core import execute, fetchone, fetchall

logger = logging.getLogger(__name__)

async def create_admins_table(conn):
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY
        )
    ''')
    logger.info("Table 'admins' ready")

async def add_admin(user_id: int):
    await execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (user_id,))

async def remove_admin(user_id: int):
    await execute('DELETE FROM admins WHERE user_id = ?', (user_id,))

async def is_admin(user_id: int) -> bool:
    row = await fetchone('SELECT 1 FROM admins WHERE user_id = ?', (user_id,))
    return row is not None

async def get_all_admins() -> List[int]:
    rows = await fetchall('SELECT user_id FROM admins')
    return [row[0] for row in rows]