"""
Инициализация модуля хендлеров.
Экспортирует роутеры для подключения к диспетчеру.
"""

from .start import router as start_router
from .order import router as order_router
from .balance import router as balance_router
from .admin import router as admin_router
from .payment import router as payment_router
from .common import router as common_router

__all__ = [
    'start_router',
    'order_router',
    'balance_router',
    'admin_router',
    'payment_router',
    'common_router',
]