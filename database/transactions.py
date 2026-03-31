import logging
from typing import List, Tuple
from .core import execute, fetchall

logger = logging.getLogger(__name__)

async def create_transactions_table(conn):
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            method TEXT,
            status TEXT,
            payment_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    logger.info("Table 'transactions' ready")

async def add_transaction(user_id: int, amount: float, method: str, status: str, payment_id: str = None):
    await execute(
        'INSERT INTO transactions (user_id, amount, method, status, payment_id) VALUES (?, ?, ?, ?, ?)',
        (user_id, amount, method, status, payment_id)
    )

async def get_transactions(user_id: int, limit: int = 20) -> List[Tuple]:
    return await fetchall(
        'SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?',
        (user_id, limit)
    )

async def get_all_transactions(limit: int = 100) -> List[Tuple]:
    return await fetchall('SELECT * FROM transactions ORDER BY created_at DESC LIMIT ?', (limit,))