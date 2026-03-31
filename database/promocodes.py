import logging
from typing import Optional, Tuple
from .core import execute, fetchone

logger = logging.getLogger(__name__)

async def create_promocodes_table(conn):
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS promocodes (
            code TEXT PRIMARY KEY,
            discount_percent INTEGER,
            uses INTEGER DEFAULT 0,
            max_uses INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    logger.info("Table 'promocodes' ready")

async def add_promocode(code: str, discount_percent: int, max_uses: int = None):
    await execute('INSERT INTO promocodes (code, discount_percent, max_uses) VALUES (?, ?, ?)',
                  (code, discount_percent, max_uses))

async def get_promocode(code: str) -> Optional[Tuple]:
    return await fetchone('SELECT * FROM promocodes WHERE code = ?', (code,))

async def use_promocode(code: str):
    await execute('UPDATE promocodes SET uses = uses + 1 WHERE code = ?', (code,))