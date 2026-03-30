import os

# Токен бота
BOT_TOKEN = os.getenv("BOT_TOKEN", "8739996462:AAFmLK0Fn7cFAJ3QpnC2BEoWERE0s_ixACw")

# ID владельца (только он может управлять админами и глобальными настройками)
OWNER_ID = int(os.getenv("OWNER_ID", "6384359588"))

# Статический список администраторов (дополнительные админы могут быть в БД)
ADMINS = [int(x) for x in os.getenv("ADMINS", "6384359588").split(",") if x]

# ЮKassa
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "1295765")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "test_W6lncrq6m_3IfpjMqCBLPUzpqcVm6BiHcKAJZ_y-yos")
YOOKASSA_RETURN_URL = os.getenv("YOOKASSA_RETURN_URL", "https://t.me/nBoostBot")

# Heleket
HELEKET_MERCHANT_ID = os.getenv("HELEKET_MERCHANT_ID", "0c2dceb5-6400-4678-ad6a-52922d3d4ea4")
HELEKET_API_KEY = os.getenv("HELEKET_API_KEY", "vzBZhgi7O2gWduZltxTWWtLiwORxOzMwuP0iOQDTrI4FiaaopymkGQ87x6pM4ooWzxOGrfwwa3NatMJctWGuwNzM9ov1PUdM1DGPau8AqSSnarEQoNopKDnPHRjVney3")
HELEKET_API_URL = os.getenv("HELEKET_API_URL", "https://api.heleket.com/v1")
HELEKET_RETURN_URL = os.getenv("HELEKET_RETURN_URL", "https://t.me/nBoostBot")

# Пути к файлам
PHOTO_PATH = "photo.jpg"
DB_PATH = "bot_database.db"
LOG_DIR = "logs"

# Значения по умолчанию для настроек (используются при первом запуске)
DEFAULT_SETTINGS = {
    "min_topup_yookassa": "10.0",
    "min_topup_heleket": "10.0",
    "default_price": "1.0",
    "currency": "RUB",
}