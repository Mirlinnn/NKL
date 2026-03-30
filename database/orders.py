"""
Модуль работы с заказами.
"""

from typing import Optional, List, Tuple
from .core import execute, fetchone, fetchall

async def create_orders_table(conn):
    """Создаёт таблицу orders."""
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            user_id INTEGER,
            service_id INTEGER,
            quantity INTEGER,
            price REAL,
            link TEXT,
            status TEXT DEFAULT 'WAITING_CONFIRM',
            comment TEXT,
            payment_id TEXT,
            payment_charge_id TEXT,
            payment_method TEXT,
            promocode TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Добавляем недостающие колонки
    for col, col_type in [
        ('service_id', 'INTEGER'),
        ('payment_id', 'TEXT'),
        ('payment_charge_id', 'TEXT'),
        ('payment_method', 'TEXT'),
        ('promocode', 'TEXT'),
        ('comment', 'TEXT')
    ]:
        try:
            await conn.execute(f'SELECT {col} FROM orders LIMIT 1')
        except:
            await conn.execute(f'ALTER TABLE orders ADD COLUMN {col} {col_type}')
    logger.info("Table 'orders' ready")

async def create_order(order_id: str, user_id: int, service_id: int, quantity: int, price: float, link: str,
                       status: str = "WAITING_CONFIRM", comment: str = None, promocode: str = None):
    """Создаёт новый заказ."""
    await execute(
        'INSERT INTO orders (order_id, user_id, service_id, quantity, price, link, status, comment, promocode) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (order_id, user_id, service_id, quantity, price, link, status, comment, promocode)
    )

async def get_order(order_id: str) -> Optional[Tuple]:
    """Возвращает заказ по ID."""
    return await fetchone('SELECT * FROM orders WHERE order_id = ?', (order_id,))

async def update_order_status(order_id: str, status: str, comment: str = None):
    """Обновляет статус заказа и комментарий."""
    await execute('UPDATE orders SET status = ?, comment = ? WHERE order_id = ?', (status, comment, order_id))

async def update_order_payment_id(order_id: str, payment_id: str):
    """Сохраняет ID платежа."""
    await execute('UPDATE orders SET payment_id = ? WHERE order_id = ?', (payment_id, order_id))

async def update_order_payment_method(order_id: str, method: str):
    """Сохраняет метод оплаты."""
    await execute('UPDATE orders SET payment_method = ? WHERE order_id = ?', (method, order_id))

async def get_orders_by_status(status: str) -> List[Tuple]:
    """Возвращает все заказы с указанным статусом."""
    return await fetchall('SELECT * FROM orders WHERE status = ?', (status,))