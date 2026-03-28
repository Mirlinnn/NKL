import aiosqlite
import logging
from datetime import datetime, timedelta

DB_PATH = "bot_database.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Таблица пользователей
        await db.execute('''
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
        # Таблица услуг
        await db.execute('''
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT,
                category TEXT,
                subcategory TEXT,
                name TEXT,
                price REAL DEFAULT 1.0,
                speed INTEGER DEFAULT 2,
                description TEXT,
                min_quantity INTEGER,
                max_quantity INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Таблица промокодов
        await db.execute('''
            CREATE TABLE IF NOT EXISTS promocodes (
                code TEXT PRIMARY KEY,
                discount_percent INTEGER,
                uses INTEGER DEFAULT 0,
                max_uses INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Таблица заказов
        await db.execute('''
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
        # Таблица транзакций
        await db.execute('''
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
        # Таблица администраторов
        await db.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            )
        ''')
        # Таблица состояния бота
        await db.execute('''
            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        await db.execute('INSERT OR IGNORE INTO bot_state (key, value) VALUES ("active", "1")')
        await db.execute('INSERT OR IGNORE INTO bot_state (key, value) VALUES ("reason", "")')
        await db.commit()
    logging.info("Database initialized.")

# ====== Состояние бота ======
async def is_bot_active() -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT value FROM bot_state WHERE key = "active"') as cursor:
            row = await cursor.fetchone()
            return row and row[0] == "1"

async def get_bot_status() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT key, value FROM bot_state') as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}

async def set_bot_active(active: bool, reason: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE bot_state SET value = ? WHERE key = "active"', ("1" if active else "0",))
        await db.execute('UPDATE bot_state SET value = ? WHERE key = "reason"', (reason,))
        await db.commit()

# ====== Пользователи ======
async def add_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
        await db.commit()

async def get_balance(user_id: int) -> float:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0.0

async def update_balance(user_id: int, amount: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
        await db.commit()

async def set_balance(user_id: int, amount: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET balance = ? WHERE user_id = ?', (amount, user_id))
        await db.commit()

async def is_banned(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT banned FROM users WHERE user_id = ?', (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row and row[0] == 1

async def get_ban_info(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT banned, banned_by, banned_at, ban_reason FROM users WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone()

async def ban_user(user_id: int, admin_id: int, reason: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'UPDATE users SET banned = 1, banned_by = ?, banned_at = datetime("now"), ban_reason = ? WHERE user_id = ?',
            (admin_id, reason, user_id)
        )
        await db.commit()

async def unban_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET banned = 0, banned_by = NULL, banned_at = NULL, ban_reason = NULL WHERE user_id = ?', (user_id,))
        await db.commit()

async def has_accepted_terms(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT accepted_terms FROM users WHERE user_id = ?', (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row and row[0] == 1

async def accept_terms(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET accepted_terms = 1 WHERE user_id = ?', (user_id,))
        await db.commit()

async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT user_id FROM users') as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

# ====== Услуги ======
async def add_service(platform: str, category: str, subcategory: str, name: str, price: float, min_q: int, max_q: int, speed: int = 2, description: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'INSERT INTO services (platform, category, subcategory, name, price, min_quantity, max_quantity, speed, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (platform, category, subcategory, name, price, min_q, max_q, speed, description)
        )
        await db.commit()
        return cursor.lastrowid

async def get_service(service_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT * FROM services WHERE id = ?', (service_id,)) as cursor:
            return await cursor.fetchone()

async def get_services_by_platform(platform: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT * FROM services WHERE platform = ?', (platform,)) as cursor:
            return await cursor.fetchall()

async def get_services_by_category(platform: str, category: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT * FROM services WHERE platform = ? AND category = ?', (platform, category)) as cursor:
            return await cursor.fetchall()

async def get_services_by_subcategory(platform: str, category: str, subcategory: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT * FROM services WHERE platform = ? AND category = ? AND subcategory = ?', (platform, category, subcategory)) as cursor:
            return await cursor.fetchall()

async def update_service_price(service_id: int, price: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE services SET price = ? WHERE id = ?', (price, service_id))
        await db.commit()

async def update_service_speed(service_id: int, speed: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE services SET speed = ? WHERE id = ?', (speed, service_id))
        await db.commit()

async def update_service_description(service_id: int, description: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE services SET description = ? WHERE id = ?', (description, service_id))
        await db.commit()

async def update_all_prices(discount_percent: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE services SET price = price * (1 - ?/100.0)', (discount_percent,))
        await db.commit()

# ====== Промокоды ======
async def add_promocode(code: str, discount_percent: int, max_uses: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT INTO promocodes (code, discount_percent, max_uses) VALUES (?, ?, ?)',
                         (code, discount_percent, max_uses))
        await db.commit()

async def get_promocode(code: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT * FROM promocodes WHERE code = ?', (code,)) as cursor:
            return await cursor.fetchone()

async def use_promocode(code: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE promocodes SET uses = uses + 1 WHERE code = ?', (code,))
        await db.commit()

# ====== Заказы ======
async def create_order(order_id: str, user_id: int, service_id: int, quantity: int, price: float, link: str,
                       status: str = "WAITING_CONFIRM", comment: str = None, promocode: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO orders (order_id, user_id, service_id, quantity, price, link, status, comment, promocode) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (order_id, user_id, service_id, quantity, price, link, status, comment, promocode)
        )
        await db.commit()

async def get_order(order_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT * FROM orders WHERE order_id = ?', (order_id,)) as cursor:
            return await cursor.fetchone()

async def update_order_status(order_id: str, status: str, comment: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE orders SET status = ?, comment = ? WHERE order_id = ?', (status, comment, order_id))
        await db.commit()

async def update_order_payment_id(order_id: str, payment_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE orders SET payment_id = ? WHERE order_id = ?', (payment_id, order_id))
        await db.commit()

async def update_order_payment_method(order_id: str, method: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE orders SET payment_method = ? WHERE order_id = ?', (method, order_id))
        await db.commit()

async def get_orders_by_status(status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT * FROM orders WHERE status = ?', (status,)) as cursor:
            return await cursor.fetchall()

# ====== Транзакции ======
async def add_transaction(user_id: int, amount: float, method: str, status: str, payment_id: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO transactions (user_id, amount, method, status, payment_id) VALUES (?, ?, ?, ?, ?)',
            (user_id, amount, method, status, payment_id)
        )
        await db.commit()

async def get_transactions(user_id: int, limit: int = 20):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            'SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?',
            (user_id, limit)
        ) as cursor:
            return await cursor.fetchall()

async def get_all_transactions(limit: int = 100):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT * FROM transactions ORDER BY created_at DESC LIMIT ?', (limit,)) as cursor:
            return await cursor.fetchall()

# ====== Статистика ======
async def get_user_count():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM users') as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def get_completed_orders():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM orders WHERE status = "PAID" OR status = "ACCEPTED"') as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def get_revenue(start_date: datetime, end_date: datetime = None):
    if end_date is None:
        end_date = datetime.now()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            'SELECT SUM(price) FROM orders WHERE status IN ("PAID", "ACCEPTED") AND created_at BETWEEN ? AND ?',
            (start_date, end_date)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row[0] else 0.0

# ====== Администраторы ======
async def add_admin(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (user_id,))
        await db.commit()

async def remove_admin(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM admins WHERE user_id = ?', (user_id,))
        await db.commit()

async def is_admin(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone() is not None

async def get_all_admins():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT user_id FROM admins') as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]