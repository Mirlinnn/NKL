import aiosqlite
import logging

DB_PATH = "bot_database.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Таблица пользователей с полем balance
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                banned INTEGER DEFAULT 0,
                accepted_terms INTEGER DEFAULT 0,
                balance REAL DEFAULT 0
            )
        ''')
        # Проверяем наличие колонки balance
        try:
            await db.execute('SELECT balance FROM users LIMIT 1')
        except aiosqlite.OperationalError:
            await db.execute('ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0')
            logging.info("Column 'balance' added to users table.")

        # Таблица заказов
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
                payment_method TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Проверяем наличие всех колонок
        for col in ['payment_id', 'payment_charge_id', 'payment_method', 'comment']:
            try:
                await db.execute(f'SELECT {col} FROM orders LIMIT 1')
            except aiosqlite.OperationalError:
                await db.execute(f'ALTER TABLE orders ADD COLUMN {col} TEXT')
                logging.info(f"Column '{col}' added to orders table.")

        # Таблица транзакций (история пополнений)
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
        await db.commit()
    logging.info("Database initialized.")

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

# Остальные функции пользователей (banned, accepted_terms) остаются без изменений
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
async def create_order(order_id: str, user_id: int, service: str, quantity: int, price: float, link: str, status: str = "NEW", comment: str = None, payment_method: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO orders (order_id, user_id, service, quantity, price, link, status, comment, payment_method) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (order_id, user_id, service, quantity, price, link, status, comment, payment_method)
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

async def update_order_payment_method(order_id: str, method: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'UPDATE orders SET payment_method = ? WHERE order_id = ?',
            (method, order_id)
        )
        await db.commit()

async def get_pending_orders():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT * FROM orders WHERE status = ?', ("PENDING",)) as cursor:
            return await cursor.fetchall()

# ====== Транзакции ======
async def add_transaction(user_id: int, amount: float, method: str, status: str, payment_id: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO transactions (user_id, amount, method, status, payment_id) VALUES (?, ?, ?, ?, ?)',
            (user_id, amount, method, status, payment_id)
        )
        await db.commit()

async def get_transactions(user_id: int, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            'SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?',
            (user_id, limit)
        ) as cursor:
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