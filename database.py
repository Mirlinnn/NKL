import aiosqlite
import datetime

DB_NAME = "shop.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            banned INTEGER DEFAULT 0
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            service TEXT,
            quantity INTEGER,
            price REAL,
            link TEXT,
            status TEXT,
            admin_action TEXT,
            created_at TEXT
        )
        """)

        await db.commit()


async def add_user(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user_id,))
        await db.commit()


async def is_banned(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT banned FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            return row and row[0] == 1


async def ban_user(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET banned=1 WHERE user_id=?", (user_id,))
        await db.commit()


async def unban_user(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET banned=0 WHERE user_id=?", (user_id,))
        await db.commit()


async def create_order(user_id, service, quantity, price, link):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
        INSERT INTO orders(user_id, service, quantity, price, link, status, created_at)
        VALUES(?,?,?,?,?,?,?)
        """, (user_id, service, quantity, price, link, "WAIT_PAYMENT", str(datetime.datetime.now())))
        await db.commit()
        return cursor.lastrowid


async def update_order_status(order_id, status, admin_action):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        UPDATE orders SET status=?, admin_action=? WHERE id=?
        """, (status, admin_action, order_id))
        await db.commit()


async def get_order(order_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM orders WHERE id=?", (order_id,)) as cur:
            return await cur.fetchone()