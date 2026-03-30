from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_main_keyboard():
    """Клавиатура главного меню."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 Заказать накрутку", callback_data="order")
    builder.button(text="🧮 Калькулятор", callback_data="calc")
    builder.button(text="💰 Баланс", callback_data="balance")
    builder.button(text="🛠 Тех. Поддержка", callback_data="support")
    builder.button(text="❓ Частые вопросы", callback_data="faq")
    builder.adjust(1)
    return builder.as_markup()

def get_back_keyboard():
    """Клавиатура с одной кнопкой «Назад»."""
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="back_to_main")
    return builder.as_markup()