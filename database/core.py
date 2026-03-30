"""
Модуль ядра базы данных.
Содержит низкоуровневые функции для работы с SQLite, пул соединений и транзакции.
"""

import aiosqlite
import logging
from contextlib import asynccontextmanager
from typing import Any, Optional, List, Tuple, Dict

from config import DB_PATH

logger = logging.getLogger(__name__)

# Пул соединений (простой, без ограничений, но можно настроить)
_connection_pool = None


async def get_connection() -> aiosqlite.Connection:
    """
    Возвращает новое соединение с базой данных.
    Если пул не создан, создаёт его (ленивая инициализация).
    """
    global _connection_pool
    if _connection_pool is None:
        # Создаём пул с одним соединением по умолчанию (можно увеличить)
        _connection_pool = aiosqlite.connect(DB_PATH)
    return _connection_pool


@asynccontextmanager
async def transaction():
    """
    Контекстный менеджер для выполнения операций в транзакции.
    Использование:
        async with transaction() as conn:
            await conn.execute(...)
    """
    conn = await get_connection()
    try:
        await conn.execute("BEGIN")
        yield conn
        await conn.commit()
    except Exception as e:
        await conn.rollback()
        logger.error(f"Transaction rolled back: {e}")
        raise
    finally:
        # Не закрываем соединение, чтобы можно было использовать повторно
        pass


async def execute(query: str, params: Optional[Tuple] = None, conn: aiosqlite.Connection = None) -> aiosqlite.Cursor:
    """
    Выполняет SQL-запрос без возврата данных (INSERT, UPDATE, DELETE).
    Если передан conn, использует его, иначе создаёт новое соединение.
    """
    close_after = False
    if conn is None:
        conn = await get_connection()
        close_after = True
    try:
        cursor = await conn.execute(query, params or ())
        await conn.commit()
        return cursor
    finally:
        if close_after:
            await conn.close()


async def fetchone(query: str, params: Optional[Tuple] = None, conn: aiosqlite.Connection = None) -> Optional[Tuple]:
    """
    Возвращает одну строку результата запроса.
    """
    close_after = False
    if conn is None:
        conn = await get_connection()
        close_after = True
    try:
        cursor = await conn.execute(query, params or ())
        return await cursor.fetchone()
    finally:
        if close_after:
            await conn.close()


async def fetchall(query: str, params: Optional[Tuple] = None, conn: aiosqlite.Connection = None) -> List[Tuple]:
    """
    Возвращает все строки результата запроса.
    """
    close_after = False
    if conn is None:
        conn = await get_connection()
        close_after = True
    try:
        cursor = await conn.execute(query, params or ())
        return await cursor.fetchall()
    finally:
        if close_after:
            await conn.close()


async def execute_many(query: str, params_list: List[Tuple], conn: aiosqlite.Connection = None) -> None:
    """
    Выполняет массовую вставку или обновление.
    """
    close_after = False
    if conn is None:
        conn = await get_connection()
        close_after = True
    try:
        await conn.executemany(query, params_list)
        await conn.commit()
    finally:
        if close_after:
            await conn.close()


async def init_db():
    """
    Инициализирует базу данных, создавая все таблицы, если они не существуют.
    Вызывает функции создания таблиц из соответствующих модулей.
    """
    # Импортируем функции создания таблиц (они будут определены в соответствующих модулях)
    from .users import create_users_table
    from .orders import create_orders_table
    from .services import create_services_table
    from .promocodes import create_promocodes_table
    from .transactions import create_transactions_table
    from .admins import create_admins_table
    from .bot_state import create_bot_state_table
    from .settings_db import create_settings_table

    conn = await get_connection()
    try:
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
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise