from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_platform_keyboard():
    """Клавиатура выбора платформы."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📱 Telegram", callback_data="platform_telegram")
    builder.button(text="📘 VK", callback_data="platform_vk")
    builder.button(text="📷 Instagram", callback_data="platform_instagram")
    builder.button(text="🎵 TikTok", callback_data="platform_tiktok")
    builder.button(text="⭐ Telegram Звёзды/Премиум", callback_data="platform_stars")
    builder.button(text="◀️ Вернуться назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()