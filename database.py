import aiosqlite
import logging

DB_PATH = "bot_database.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Создаём таблицу users, если её нет
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                banned INTEGER DEFAULT 0
            )
        ''')

        # Проверяем, есть ли колонка accepted_terms
        try:
            await db.execute('SELECT accepted_terms FROM users LIMIT 1')
        except aiosqlite.OperationalError:
            # Если нет — добавляем
            await db.execute('ALTER TABLE users ADD COLUMN accepted_terms INTEGER DEFAULT 0')
            logging.info("Column 'accepted_terms' added to users table.")

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

# Остальные функции без изменений (add_user, is_banned, ban_user, unban_user, has_accepted_terms, accept_terms, get_all_users, create_order, get_order, update_order_status, get_all_admins, add_admin, remove_admin, is_admin)
# ... (скопируйте их из предыдущего ответа)