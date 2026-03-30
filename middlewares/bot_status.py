from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, CallbackQuery, Message
from typing import Callable, Dict, Any, Awaitable
from database.bot_state import is_bot_active
from config import OWNER_ID
from utils.cache import get_admins

class BotStatusMiddleware(BaseMiddleware):
    """Middleware для проверки активности бота (для обычных пользователей)."""
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        admins = await get_admins()
        if user.id in admins or user.id == OWNER_ID:
            return await handler(event, data)

        if not await is_bot_active():
            bot = data.get("bot")
            if bot and isinstance(event, (CallbackQuery, Message)):
                try:
                    await event.answer("❌ Бот временно недоступен. Попробуйте позже.", show_alert=True)
                except:
                    pass
            return

        return await handler(event, data)