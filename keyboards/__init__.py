from .main import get_main_keyboard, get_back_keyboard
from .platforms import get_platform_keyboard
from .telegram import get_telegram_menu
from .vk import get_vk_menu
from .instagram import get_instagram_menu
from .tiktok import get_tiktok_menu
from .stars import get_stars_menu

__all__ = [
    'get_main_keyboard',
    'get_back_keyboard',
    'get_platform_keyboard',
    'get_telegram_menu',
    'get_vk_menu',
    'get_instagram_menu',
    'get_tiktok_menu',
    'get_stars_menu',
]