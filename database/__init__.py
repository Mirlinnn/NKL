"""
Инициализация модуля базы данных.
Экспортирует все основные функции и классы для работы с БД.
"""

from .core import (
    init_db,
    get_connection,
    execute,
    fetchone,
    fetchall,
    execute_many,
    transaction
)

from .users import (
    add_user,
    get_balance,
    update_balance,
    set_balance,
    is_banned,
    get_ban_info,
    ban_user,
    unban_user,
    has_accepted_terms,
    accept_terms,
    get_all_users
)

from .orders import (
    create_order,
    get_order,
    update_order_status,
    update_order_payment_id,
    update_order_payment_method,
    get_orders_by_status
)

from .services import (
    add_service,
    get_service,
    get_services_by_platform,
    get_services_by_category,
    get_services_by_subcategory,
    update_service_price,
    update_service_speed,
    update_service_description,
    update_all_prices
)

from .promocodes import (
    add_promocode,
    get_promocode,
    use_promocode
)

from .transactions import (
    add_transaction,
    get_transactions,
    get_all_transactions
)

from .admins import (
    add_admin,
    remove_admin,
    is_admin,
    get_all_admins
)

from .bot_state import (
    is_bot_active,
    get_bot_status,
    set_bot_active
)

from .settings_db import (
    init_settings_table,
    get_setting,
    set_setting,
    get_all_settings
)