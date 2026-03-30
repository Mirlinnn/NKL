import logging
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable

logger = logging.getLogger(__name__)

class LoggingMiddleware(BaseMiddleware):
    """Middleware для логирования всех входящих обновлений."""
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if isinstance(event, Message):
            logger.info(f"Message from {user.id}: {event.text}")
        elif isinstance(event, CallbackQuery):
            logger.info(f"Callback from {user.id}: {event.data}")
        else:
            logger.debug(f"Update type: {type(event)}")

        return await handler(event, data)