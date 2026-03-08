import aiosqlite
import logging

DB_PATH = "bot_database.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Таблица пользователей
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                banned INTEGER DEFAULT 0
            )
        ''')
        try:
            await db.execute('SELECT accepted_terms FROM users LIMIT 1')
        except aiosqlite.OperationalError:
            await db.execute('ALTER TABLE users ADD COLUMN accepted_terms INTEGER DEFAULT 0')
            logging.info("Column 'accepted_terms' added to users table.")

        # Таблица заказов с явным указанием всех полей
        await db.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                user_id INTEGER,
                service TEXT,
                quantity INTEGER,
                price REAL,
                link TEXT,
                status TEXT DEFAULT 'NEW',
                comment TEXT,
                payment_id TEXT,
                payment_charge_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Проверяем наличие колонки payment_id (на случай старых БД)
        try:
            await db.execute('SELECT payment_id FROM orders LIMIT 1')
        except aiosqlite.OperationalError:
            await db.execute('ALTER TABLE orders ADD COLUMN payment_id TEXT')
            logging.info("Column 'payment_id' added to orders table.")

        try:
            await db.execute('SELECT payment_charge_id FROM orders LIMIT 1')
        except aiosqlite.OperationalError:
            await db.execute('ALTER TABLE orders ADD COLUMN payment_charge_id TEXT')
            logging.info("Column 'payment_charge_id' added to orders table.")

        # Таблица администраторов
        await db.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            )
        ''')
        await db.commit()
    logging.info("Database initialized.")

# ====== Пользователи ======
async def add_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
        await db.commit()

async def is_banned(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT banned FROM users WHERE user_id = ?', (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row and row[0] == 1

async def ban_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET banned = 1 WHERE user_id = ?', (user_id,))
        await db.commit()

async def unban_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET banned = 0 WHERE user_id = ?', (user_id,))
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

# ====== Заказы ======
async def create_order(order_id: str, user_id: int, service: str, quantity: int, price: float, link: str, status: str = "NEW"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO orders (order_id, user_id, service, quantity, price, link, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (order_id, user_id, service, quantity, price, link, status)
        )
        await db.commit()

async def create_order_with_payment(order_id: str, user_id: int, service: str, quantity: int, price: float, link: str, payment_id: str, status: str = "PENDING"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO orders (order_id, user_id, service, quantity, price, link, status, payment_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (order_id, user_id, service, quantity, price, link, status, payment_id)
        )
        await db.commit()

async def get_order(order_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT * FROM orders WHERE order_id = ?', (order_id,)) as cursor:
            return await cursor.fetchone()

async def update_order_status(order_id: str, status: str, comment: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'UPDATE orders SET status = ?, comment = ? WHERE order_id = ?',
            (status, comment, order_id)
        )
        await db.commit()

async def update_order_payment_id(order_id: str, payment_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'UPDATE orders SET payment_id = ? WHERE order_id = ?',
            (payment_id, order_id)
        )
        await db.commit()

async def get_pending_orders():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT * FROM orders WHERE status = ?', ("PENDING",)) as cursor:
            return await cursor.fetchall()

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