from aiocache import cached, Cache
from aiocache.serializers import JsonSerializer
import database.admins as db_admins
import database.settings_db as db_settings

@cached(ttl=60, cache=Cache.MEMORY, serializer=JsonSerializer())
async def get_admins():
    """Возвращает список ID администраторов (с кэшированием на 60 секунд)."""
    return await db_admins.get_all_admins()

async def invalidate_admins():
    """Сбросить кэш списка администраторов."""
    await get_admins.invalidate()

@cached(ttl=300, cache=Cache.MEMORY, serializer=JsonSerializer())
async def get_settings():
    """Возвращает словарь настроек (с кэшированием на 5 минут)."""
    return await db_settings.get_all_settings()

async def invalidate_settings():
    """Сбросить кэш настроек."""
    await get_settings.invalidate()