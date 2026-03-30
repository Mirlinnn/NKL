import random
import string
from config import OWNER_ID, ADMINS as STATIC_ADMINS
import database.admins as db_admins

def generate_order_id(length=6):
    """Генерирует случайный ID заказа."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def validate_link(link: str) -> bool:
    """Проверяет, начинается ли ссылка с http:// или https://."""
    return link.startswith(("http://", "https://"))

async def is_owner(user_id: int) -> bool:
    """Проверяет, является ли пользователь владельцем."""
    return user_id == OWNER_ID

async def is_admin_from_db_or_config(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором (статическим или из БД)."""
    if user_id in STATIC_ADMINS:
        return True
    return await db_admins.is_admin(user_id)