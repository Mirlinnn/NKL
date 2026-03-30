from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, CallbackQuery, Message
from typing import Callable, Dict, Any, Awaitable
import database.users as db_users
from config import OWNER_ID
from utils.cache import get_admins

class BanCheckMiddleware(BaseMiddleware):
    """Middleware для проверки бана пользователя."""
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        # Админы и владелец не проверяются на бан
        admins = await get_admins()
        if user.id in admins or user.id == OWNER_ID:
            return await handler(event, data)

        # Проверка бана
        if await db_users.is_banned(user.id):
            # Отвечаем, если событие поддерживает ответ
            if isinstance(event, (CallbackQuery, Message)):
                try:
                    await event.answer("❌ Вы заблокированы.", show_alert=True)
                except:
                    pass
            return

        return await handler(event, data)