"""
Модуль ядра базы данных.
Содержит низкоуровневые функции для работы с SQLite.
"""

import aiosqlite
import logging
from contextlib import asynccontextmanager
from typing import Any, Optional, List, Tuple

from config import DB_PATH

logger = logging.getLogger(__name__)

@asynccontextmanager
async def get_connection():
    """Контекстный менеджер для соединения с базой."""
    async with aiosqlite.connect(DB_PATH) as conn:
        yield conn

@asynccontextmanager
async def transaction():
    """Контекстный менеджер для выполнения операций в транзакции."""
    async with aiosqlite.connect(DB_PATH) as conn:
        try:
            await conn.execute("BEGIN")
            yield conn
            await conn.commit()
        except Exception as e:
            await conn.rollback()
            logger.error(f"Transaction rolled back: {e}")
            raise

async def execute(query: str, params: Optional[Tuple] = None):
    """Выполняет SQL-запрос без возврата данных (INSERT, UPDATE, DELETE)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(query, params or ())
        await conn.commit()

async def fetchone(query: str, params: Optional[Tuple] = None) -> Optional[Tuple]:
    """Возвращает одну строку результата запроса."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(query, params or ())
        return await cursor.fetchone()

async def fetchall(query: str, params: Optional[Tuple] = None) -> List[Tuple]:
    """Возвращает все строки результата запроса."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(query, params or ())
        return await cursor.fetchall()

async def execute_many(query: str, params_list: List[Tuple]) -> None:
    """Выполняет массовую вставку или обновление."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.executemany(query, params_list)
        await conn.commit()

async def init_db():
    """
    Инициализирует базу данных, создавая все таблицы, если они не существуют.
    Вызывает функции создания таблиц из соответствующих модулей.
    """
    from .users import create_users_table
    from .orders import create_orders_table
    from .services import create_services_table
    from .promocodes import create_promocodes_table
    from .transactions import create_transactions_table
    from .admins import create_admins_table
    from .bot_state import create_bot_state_table
    from .settings_db import create_settings_table

    async with aiosqlite.connect(DB_PATH) as conn:
        await create_users_table(conn)
        await create_orders_table(conn)
        await create_services_table(conn)
        await create_promocodes_table(conn)
        await create_transactions_table(conn)
        await create_admins_table(conn)
        await create_bot_state_table(conn)
        await create_settings_table(conn)
        await conn.commit()
        logger.info("Database tables initialized")