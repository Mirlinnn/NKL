from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.exceptions import TelegramForbiddenError
import logging
import asyncio
from datetime import datetime, timedelta
from bot_instance import bot

from config import OWNER_ID, ADMINS as STATIC_ADMINS
import database as db
from states.states import BanReason, StopOrderReason, BroadcastState
from utils.helpers import is_owner, is_admin_from_db_or_config
import settings

router = Router()
logger = logging.getLogger(__name__)

# ====== Управление пользователями ======
@router.message(Command("ban"))
async def ban_cmd(message: Message, state: FSMContext):
    if not await is_admin_from_db_or_config(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Использование: /ban <user_id> [причина]")
    try:
        user_id = int(args[1])
    except ValueError:
        return await message.answer("ID должен быть числом.")
    if len(args) >= 3:
        reason = " ".join(args[2:])
        await db.ban_user(user_id, message.from_user.id, reason)
        await message.answer(f"Пользователь {user_id} забанен.\nПричина: {reason}")
        try:
            await bot.send_message(user_id, f"❌ Вы заблокированы.\nПричина: {reason}")
        except:
            pass
    else:
        await state.update_data(ban_user_id=user_id)
        await message.answer("Введите причину бана:")
        await state.set_state(BanReason.waiting_reason)

@router.message(BanReason.waiting_reason)
async def ban_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("ban_user_id")
    reason = message.text.strip()
    await db.ban_user(user_id, message.from_user.id, reason)
    await message.answer(f"Пользователь {user_id} забанен.\nПричина: {reason}")
    try:
        await bot.send_message(user_id, f"❌ Вы заблокированы.\nПричина: {reason}")
    except:
        pass
    await state.clear()

@router.message(Command("unban"))
async def unban_cmd(message: Message):
    if not await is_admin_from_db_or_config(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Использование: /unban <user_id>")
    try:
        user_id = int(args[1])
    except ValueError:
        return await message.answer("ID должен быть числом.")
    await db.unban_user(user_id)
    await message.answer(f"Пользователь {user_id} разбанен.")
    try:
        await bot.send_message(user_id, "✅ Вы разблокированы. Теперь вы можете пользоваться ботом.")
    except:
        pass

@router.message(Command("checkban"))
async def check_ban(message: Message):
    if not await is_admin_from_db_or_config(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Использование: /checkban <user_id>")
    try:
        user_id = int(args[1])
    except ValueError:
        return await message.answer("ID должен быть числом.")
    ban_info = await db.get_ban_info(user_id)
    if not ban_info or ban_info[0] == 0:
        await message.answer(f"Пользователь {user_id} не забанен.")
        return
    banned_by = ban_info[1] or "неизвестно"
    banned_at = ban_info[2] or "неизвестно"
    reason = ban_info[3] or "Не указана"
    await message.answer(
        f"🔍 Информация о бане пользователя {user_id}:\n"
        f"Забанен: ✅\n"
        f"Кто забанил: {banned_by}\n"
        f"Дата: {banned_at}\n"
        f"Причина: {reason}"
    )

# ====== Управление заказами ======
@router.message(Command("search"))
async def search_order(message: Message):
    if not await is_admin_from_db_or_config(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Использование: /search <order_id>")
    order_id = args[1]
    order = await db.get_order(order_id)
    if not order:
        await message.answer("❌ Заказ не найден.")
        return

    status_text = {
        "NEW": "🆕 Новый",
        "PENDING": "⏳ Ожидает оплаты",
        "WAITING_CONFIRM": "🕒 Ожидает подтверждения",
        "PAID": "✅ Оплачен",
        "ACCEPTED": "📦 Принят в работу",
        "DECLINED": "❌ Отклонён"
    }.get(order[6], order[6])

    service_info = order[7] or "не указано"
    response = f"""
🔍 <b>Информация о заказе</b>

🆔 <b>Номер заказа:</b> {order[0]}
👤 <b>Пользователь ID:</b> {order[1]}
📦 <b>Услуга:</b> {service_info}
🔢 <b>Количество:</b> {order[3]}
💰 <b>Стоимость:</b> {order[4]:.2f} руб.
🔗 <b>Ссылка:</b> {order[5]}
📊 <b>Статус:</b> {status_text}
💳 <b>Метод оплаты:</b> {order[10] if order[10] else 'не выбран'}
🆔 <b>ID платежа:</b> {order[8] if order[8] else 'нет'}
📅 <b>Создан:</b> {order[11]}
    """
    await message.answer(response, parse_mode="HTML", disable_web_page_preview=True)

@router.message(Command("stop"))
async def stop_order(message: Message, state: FSMContext):
    if not await is_admin_from_db_or_config(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Использование: /stop <order_id> [причина]")
    order_id = args[1]
    order = await db.get_order(order_id)
    if not order:
        return await message.answer("❌ Заказ не найден.")
    if order[6] not in ("PAID", "ACCEPTED", "WAITING_CONFIRM"):
        return await message.answer("❌ Можно остановить только оплаченный, принятый или ожидающий подтверждения заказ.")
    if len(args) >= 3:
        reason = " ".join(args[2:])
        await process_stop_order(message, order, reason)
    else:
        await state.update_data(order_id=order_id, order=order)
        await message.answer("Введите причину отмены заказа:")
        await state.set_state(StopOrderReason.waiting_reason)

@router.message(StopOrderReason.waiting_reason)
async def stop_order_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    order = data['order']
    reason = message.text.strip()
    await process_stop_order(message, order, reason)
    await state.clear()

async def process_stop_order(message: Message, order, reason: str):
    order_id = order[0]
    user_id = order[1]
    price = order[4]
    if order[6] in ("PAID", "ACCEPTED"):
        await db.update_balance(user_id, price)
    await db.update_order_status(order_id, "DECLINED", f"Остановлен администратором: {reason}")
    try:
        await bot.send_message(
            user_id,
            f"❌ Ваш заказ №{order_id} был остановлен администратором.\nПричина: {reason}\n"
            + ("Средства возвращены на баланс." if order[6] in ("PAID", "ACCEPTED") else "Средства не списывались.")
        )
    except TelegramForbiddenError:
        logger.warning(f"User {user_id} blocked the bot.")
    await message.answer(f"✅ Заказ №{order_id} остановлен. Средства возвращены пользователю.")

# ====== Управление ботом ======
@router.message(Command("stopbot"))
async def stop_bot(message: Message):
    if not await is_owner(message.from_user.id):
        return
    args = message.text.split()
    reason = " ".join(args[1:]) if len(args) > 1 else "Бот временно недоступен по техническим причинам."
    await db.set_bot_active(False, reason)
    await message.answer(f"🚫 Бот остановлен. Причина: {reason}\nДоступ имеют только администраторы и владелец.")

@router.message(Command("startbot"))
async def start_bot(message: Message):
    if not await is_owner(message.from_user.id):
        return
    await db.set_bot_active(True)
    await message.answer("✅ Бот возобновил работу. Все пользователи могут пользоваться ботом.")

# ====== Управление админами ======
@router.message(Command("addadmin"))
async def add_admin(message: Message):
    if not await is_owner(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Использование: /addadmin <user_id>")
    try:
        user_id = int(args[1])
    except ValueError:
        return await message.answer("ID должен быть числом.")
    await db.add_admin(user_id)
    await message.answer(f"Пользователь {user_id} добавлен в администраторы.")

@router.message(Command("deladmin"))
async def remove_admin(message: Message):
    if not await is_owner(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Использование: /deladmin <user_id>")
    try:
        user_id = int(args[1])
    except ValueError:
        return await message.answer("ID должен быть числом.")
    await db.remove_admin(user_id)
    await message.answer(f"Пользователь {user_id} удалён из администраторов.")

@router.message(Command("admins"))
async def list_admins(message: Message):
    if not await is_owner(message.from_user.id):
        return
    admins = await db.get_all_admins()
    if not admins:
        await message.answer("Список администраторов пуст.")
        return
    text = "👑 <b>Список администраторов:</b>\n"
    for admin_id in admins:
        text += f"- {admin_id}\n"
    await message.answer(text, parse_mode="HTML")

# ====== Управление ценами и услугами ======
@router.message(Command("setprice"))
async def set_price(message: Message):
    if not await is_owner(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 3:
        return await message.answer("Использование: /setprice <id_услуги> <цена>")
    try:
        service_id = int(args[1])
        price = float(args[2])
    except ValueError:
        return await message.answer("ID услуги и цена должны быть числами.")
    await db.update_service_price(service_id, price)
    await settings.invalidate_settings()  # сброс кэша настроек
    await message.answer(f"Цена услуги #{service_id} установлена на {price:.2f} руб.")

@router.message(Command("setpriceall"))
async def set_price_all(message: Message):
    if not await is_owner(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Использование: /setpriceall <скидка_процент> (отрицательное число для повышения)")
    try:
        discount = int(args[1])
    except ValueError:
        return await message.answer("Скидка должна быть числом.")
    await db.update_all_prices(discount)
    await settings.invalidate_settings()
    await message.answer(f"✅ Все цены изменены на {discount}% {'(скидка)' if discount > 0 else '(повышение)' if discount < 0 else '(без изменений)'}")

@router.message(Command("setstat"))
async def set_speed(message: Message):
    if not await is_owner(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 3:
        return await message.answer("Использование: /setstat <id_услуги> <1-3> (1=быстро, 2=умеренно, 3=медленно)")
    try:
        service_id = int(args[1])
        speed = int(args[2])
        if speed not in (1, 2, 3):
            return await message.answer("Скорость должна быть 1 (быстро), 2 (умеренно) или 3 (медленно).")
    except ValueError:
        return await message.answer("ID услуги и скорость должны быть числами.")
    await db.update_service_speed(service_id, speed)
    speed_text = {1: "быстро", 2: "умеренно", 3: "медленно"}.get(speed)
    await message.answer(f"Скорость услуги #{service_id} установлена: {speed_text}")

@router.message(Command("settext"))
async def set_text(message: Message):
    if not await is_owner(message.from_user.id):
        return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        return await message.answer("Использование: /settext <id_услуги> <текст>")
    try:
        service_id = int(args[1])
    except ValueError:
        return await message.answer("ID услуги должен быть числом.")
    text = args[2]
    await db.update_service_description(service_id, text)
    await message.answer(f"Текст услуги #{service_id} обновлён.")

# ====== Управление балансом (только владелец) ======
@router.message(Command("addbalance"))
async def add_balance(message: Message):
    if not await is_owner(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 3:
        return await message.answer("Использование: /addbalance <user_id> <amount>")
    try:
        user_id = int(args[1])
        amount = float(args[2])
    except ValueError:
        return await message.answer("ID должен быть числом, сумма числом.")
    await db.update_balance(user_id, amount)
    await message.answer(f"Баланс пользователя {user_id} изменён на +{amount:.2f} руб.")

@router.message(Command("setbalance"))
async def set_balance(message: Message):
    if not await is_owner(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 3:
        return await message.answer("Использование: /setbalance <user_id> <amount>")
    try:
        user_id = int(args[1])
        amount = float(args[2])
    except ValueError:
        return await message.answer("ID должен быть числом, сумма числом.")
    await db.set_balance(user_id, amount)
    await message.answer(f"Баланс пользователя {user_id} установлен на {amount:.2f} руб.")

# ====== Промокоды ======
@router.message(Command("addpromo"))
async def add_promo(message: Message):
    if not await is_owner(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 3:
        return await message.answer("Использование: /addpromo <название> <скидка_процент> [макс_использований]")
    code = args[1].upper()
    try:
        discount = int(args[2])
    except ValueError:
        return await message.answer("Скидка должна быть числом.")
    max_uses = int(args[3]) if len(args) > 3 else None
    try:
        await db.add_promocode(code, discount, max_uses)
        await message.answer(f"✅ Промокод {code} создан! Скидка: {discount}%, макс. использований: {max_uses or '∞'}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

# ====== Статистика ======
@router.message(Command("statsbot"))
async def stats_bot(message: Message):
    if not await is_owner(message.from_user.id):
        return
    users_count = await db.get_user_count()
    orders_count = await db.get_completed_orders()
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0)
    week_start = now - timedelta(days=now.weekday())
    month_start = datetime(now.year, now.month, 1, 0, 0, 0)
    revenue_today = await db.get_revenue(today_start, now)
    revenue_week = await db.get_revenue(week_start, now)
    revenue_month = await db.get_revenue(month_start, now)
    revenue_all = await db.get_revenue(datetime(2020, 1, 1), now)
    admins = await db.get_all_admins()
    admins_text = ", ".join(str(a) for a in admins) if admins else "нет"
    text = f"""
📊 <b>Статистика бота</b>

👥 <b>Пользователей:</b> {users_count}
📦 <b>Выполнено заказов:</b> {orders_count}

💰 <b>Выручка:</b>
• За сегодня: {revenue_today:.2f} руб.
• За неделю: {revenue_week:.2f} руб.
• За месяц: {revenue_month:.2f} руб.
• За всё время: {revenue_all:.2f} руб.

👑 <b>Администраторы:</b> {admins_text}
    """
    await message.answer(text, parse_mode="HTML")

# ====== Рассылка ======
@router.message(Command("all"))
async def broadcast_command(message: Message, state: FSMContext):
    if not await is_owner(message.from_user.id):
        return
    await message.answer("Отправьте сообщение для рассылки всем пользователям (можно с медиа).")
    await state.set_state(BroadcastState.waiting_message)

@router.message(BroadcastState.waiting_message)
async def broadcast_message(message: Message, state: FSMContext):
    if not await is_owner(message.from_user.id):
        return await state.clear()
    users = await db.get_all_users()
    await message.answer(f"Начинаю рассылку {len(users)} пользователям...")
    semaphore = asyncio.Semaphore(50)
    sent = blocked = 0

    async def send_one(user_id):
        nonlocal sent, blocked
        async with semaphore:
            try:
                await bot.copy_message(user_id, message.chat.id, message.message_id)
                sent += 1
            except TelegramForbiddenError:
                blocked += 1
            except Exception as e:
                logger.error(f"Failed to send to {user_id}: {e}")

    await asyncio.gather(*[send_one(uid) for uid in users])
    await message.answer(f"Рассылка завершена.\nОтправлено: {sent}\nЗаблокировали бота: {blocked}")
    await state.clear()

# ====== Команды помощи ======
@router.message(Command("helpadmin"))
async def help_admin(message: Message):
    if not await is_admin_from_db_or_config(message.from_user.id):
        return
    text = """
<b>👑 Административные команды:</b>

<b>Управление пользователями:</b>
/ban <id> [причина] — заблокировать пользователя
/unban <id> — разблокировать пользователя
/checkban <id> — проверить статус бана

<b>Управление заказами:</b>
/stop <order_id> [причина] — остановить заказ (возврат средств)
/search <order_id> — поиск заказа

<b>Управление ботом:</b>
/all — массовая рассылка (только владелец)
/stopbot [причина] — временно отключить бот (только владелец)
/startbot — включить бот (только владелец)

<b>Управление админами:</b>
/addadmin <id> — добавить администратора (только владелец)
/deladmin <id> — удалить администратора (только владелец)
/admins — список администраторов (только владелец)

<b>Управление ценами и услугами (только владелец):</b>
/setprice <id> <цена> — изменить цену услуги
/setpriceall <скидка_%> — изменить все цены на %
/setstat <id> <1-3> — установить скорость (1=быстро,2=умеренно,3=медленно)
/settext <id> <текст> — изменить описание услуги

<b>Управление промокодами (только владелец):</b>
/addpromo <название> <скидка_%> [макс_использований] — создать промокод

<b>Управление балансом (только владелец):</b>
/addbalance <id> <сумма> — добавить средства
/setbalance <id> <сумма> — установить баланс

<b>Статистика (только владелец):</b>
/statsbot — статистика бота
"""
    await message.answer(text, parse_mode="HTML")

@router.message(Command("helpowner"))
async def help_owner(message: Message):
    if not await is_owner(message.from_user.id):
        return
    text = """
<b>👑 Команды владельца:</b>

<b>Управление админами:</b>
/addadmin <id> — добавить администратора
/deladmin <id> — удалить администратора
/admins — список администраторов

<b>Управление ценами и услугами:</b>
/setprice <id> <цена> — изменить цену услуги
/setpriceall <скидка_%> — изменить все цены на %
/setstat <id> <1-3> — установить скорость (1=быстро,2=умеренно,3=медленно)
/settext <id> <текст> — изменить описание услуги

<b>Управление промокодами:</b>
/addpromo <название> <скидка_%> [макс_использований] — создать промокод

<b>Управление балансом:</b>
/addbalance <id> <сумма> — добавить средства
/setbalance <id> <сумма> — установить баланс

<b>Управление ботом:</b>
/all — массовая рассылка
/stopbot [причина] — временно отключить бот
/startbot — включить бот

<b>Статистика:</b>
/statsbot — статистика бота
"""
    await message.answer(text, parse_mode="HTML")