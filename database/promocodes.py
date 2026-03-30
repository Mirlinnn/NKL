"""
Модуль работы с промокодами.
"""

from typing import Optional, Tuple
from .core import execute, fetchone

async def create_promocodes_table(conn):
    """Создаёт таблицу promocodes."""
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
    """Добавляет новый промокод."""
    await execute('INSERT INTO promocodes (code, discount_percent, max_uses) VALUES (?, ?, ?)',
                  (code, discount_percent, max_uses))

async def get_promocode(code: str) -> Optional[Tuple]:
    """Возвращает промокод по коду."""
    return await fetchone('SELECT * FROM promocodes WHERE code = ?', (code,))

async def use_promocode(code: str):
    """Увеличивает счётчик использований промокода."""
    await execute('UPDATE promocodes SET uses = uses + 1 WHERE code = ?', (code,))