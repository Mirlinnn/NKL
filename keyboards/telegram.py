from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_telegram_menu():
    """Клавиатура меню Telegram."""
    builder = InlineKeyboardBuilder()
    builder.button(text="👁 Просмотры", callback_data="tg_views")
    builder.button(text="👥 Подписчики", callback_data="tg_subscribers")
    builder.button(text="❤️ Реакции", callback_data="tg_reactions")
    builder.button(text="🔄 Дополнительно", callback_data="tg_additional")
    builder.button(text="🚀 Старты в бота", callback_data="tg_starts")
    builder.button(text="◀️ Назад к платформам", callback_data="order")
    builder.adjust(1)
    return builder.as_markup()