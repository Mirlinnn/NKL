import asyncio
import logging
import random
import string
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.exceptions import TelegramForbiddenError
from config import BOT_TOKEN, ADMINS, CARD_DETAILS, CRYPTO_DETAILS
import database

logging.basicConfig(level=logging.INFO)
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ====== Состояния ======
class OrderState(StatesGroup):
    waiting_quantity = State()
    waiting_link = State()

class CalcState(StatesGroup):
    waiting_quantity = State()

class DeclineReason(StatesGroup):
    waiting_reason = State()

# ====== Цены ======
PRICES = {
    "subscribers": 0.02,
    "views": 0.01,
    "reactions": 0.01
}

# ====== Генерация ID заказа ======
def generate_order_id(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# ====== Проверка бана ======
async def check_ban(user_id: int) -> bool:
    banned = await database.is_banned(user_id)
    if banned:
        await bot.send_message(user_id, "❌ Вы заблокированы.")
        return True
    return False

# ====== Функция показа главного меню ======
async def show_main_menu(chat_id: int, call: CallbackQuery = None):
    """Отправляет главное меню (с фото или текстом). Если передан call, удаляет его сообщение."""
    if call:
        try:
            await call.message.delete()
        except Exception:
            pass

    kb = InlineKeyboardBuilder()
    kb.button(text="🛒 Заказать накрутку", callback_data="order")
    kb.button(text="🧮 Калькулятор", callback_data="calc")
    kb.button(text="🛠 Тех. Поддержка", callback_data="support")
    kb.button(text="❓ Частые вопросы", callback_data="faq")
    kb.adjust(1)

    try:
        photo = FSInputFile("photo.jpg")
        await bot.send_photo(chat_id, photo, caption="Добро пожаловать в наш шоп 🚀", reply_markup=kb.as_markup())
    except FileNotFoundError:
        await bot.send_message(chat_id, "Добро пожаловать в наш шоп 🚀", reply_markup=kb.as_markup())

# ====== /start ======
@dp.message(Command("start"))
async def start_handler(message: Message):
    await database.add_user(message.from_user.id)
    if await check_ban(message.from_user.id):
        return
    await show_main_menu(message.chat.id)

# ====== ЗАКАЗ ======
@dp.callback_query(F.data == "order")
async def order_menu(call: CallbackQuery):
    await call.answer()
    if await check_ban(call.from_user.id):
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="Подписчики", callback_data="subscribers")
    kb.button(text="Просмотры", callback_data="views")
    kb.button(text="Реакции", callback_data="reactions")
    kb.button(text="◀️ Вернуться назад", callback_data="back_to_main")
    kb.adjust(1)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("Выберите услугу:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.in_(["subscribers", "views", "reactions"]))
async def choose_service(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban(call.from_user.id):
        return
    await state.update_data(service=call.data)
    await call.message.answer("Введите количество:")
    await state.set_state(OrderState.waiting_quantity)

@dp.message(OrderState.waiting_quantity)
async def get_quantity(message: Message, state: FSMContext):
    if await check_ban(message.from_user.id):
        return await state.clear()
    if not message.text or not message.text.isdigit():
        return await message.answer("Введите число!")
    quantity = int(message.text)
    data = await state.get_data()
    service = data["service"]
    price = quantity * PRICES[service]
    await state.update_data(quantity=quantity, price=price)
    await message.answer(f"💰 Стоимость: {price} руб.\n\nОтправьте ссылку:")
    await state.set_state(OrderState.waiting_link)

@dp.message(OrderState.waiting_link)
async def get_link(message: Message, state: FSMContext):
    if await check_ban(message.from_user.id):
        return await state.clear()
    link = message.text.strip()
    if not link.startswith(("http://", "https://")):
        return await message.answer("Пожалуйста, отправьте корректную ссылку, начинающуюся с http:// или https://")
    data = await state.get_data()
    order_id = generate_order_id()
    try:
        await database.create_order(
            order_id,
            message.from_user.id,
            data["service"],
            data["quantity"],
            data["price"],
            link
        )
    except Exception as e:
        logging.error(f"DB error: {e}")
        return await message.answer("Ошибка при создании заказа. Попробуйте позже.")
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Проверить платёж", callback_data=f"check_{order_id}")
    payment_info = ""
    if CARD_DETAILS:
        payment_info += f"\n{CARD_DETAILS}"
    if CRYPTO_DETAILS:
        payment_info += f"\n{CRYPTO_DETAILS}"
    await message.answer(
        f"""
📦 Заказ №{order_id}

Услуга: {data['service']}
Кол-во: {data['quantity']}
Цена: {data['price']} руб
Ссылка: {link}
{payment_info}
""",
        reply_markup=kb.as_markup()
    )
    await state.clear()

@dp.callback_query(F.data.startswith("check_"))
async def check_payment(call: CallbackQuery):
    await call.answer()
    if await check_ban(call.from_user.id):
        return
    order_id = call.data.split("_")[1]
    order = await database.get_order(order_id)
    if not order:
        return await call.message.answer("Заказ не найден.")
    # Индексы: 0-order_id,1-user_id,2-service,3-quantity,4-price,5-link,6-status,7-comment,8-created_at
    if order[6] not in ("NEW", "PENDING"):
        return await call.message.answer("Этот заказ уже обработан.")
    await call.message.answer("⏳ Заказ обрабатывается...")
    service_map = {"subscribers": "Подписчики", "views": "Просмотры", "reactions": "Реакции"}
    service_name = service_map.get(order[2], order[2])
    user_id = order[1]
    username = call.from_user.username or "нет username"
    text_for_admin = f"""
# НОВЫЙ ЗАКАЗ
🆔 Номер заказа: {order_id}
👤 Пользователь: {user_id} (@{username})
📦 Услуга: {service_name}
🔢 Количество: {order[3]}
💰 Сумма: {order[4]} руб.
🔗 Ссылка: {order[5]}
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Принять", callback_data=f"accept_{order_id}")
    kb.button(text="❌ Отклонить", callback_data=f"decline_{order_id}")
    for admin in ADMINS:
        try:
            await bot.send_message(admin, text_for_admin, reply_markup=kb.as_markup())
        except Exception as e:
            logging.error(f"Failed to send to admin {admin}: {e}")

@dp.callback_query(F.data.startswith("accept_"))
async def accept_order(call: CallbackQuery):
    await call.answer()
    if call.from_user.id not in ADMINS:
        return
    order_id = call.data.split("_")[1]
    order = await database.get_order(order_id)
    if not order:
        return await call.message.answer("Заказ не найден.")
    if order[6] not in ("NEW", "PENDING"):
        return await call.message.answer("Этот заказ уже обработан другим администратором.")
    await database.update_order_status(order_id, "ACCEPTED", "Принят")
    await call.message.edit_text(call.message.text + "\n\n✅ Заказ принят.", reply_markup=None)
    try:
        await bot.send_message(order[1], f"✅ Ваш заказ №{order_id} принят и будет выполнен в ближайшее время.")
    except TelegramForbiddenError:
        logging.warning(f"User {order[1]} blocked the bot.")
    except Exception as e:
        logging.error(f"Error sending to user: {e}")
    service_map = {"subscribers": "Подписчики", "views": "Просмотры", "reactions": "Реакции"}
    service_name = service_map.get(order[2], order[2])
    await call.message.answer(
        f"✅ Заказ №{order_id} выполнен.\n"
        f"👤 Пользователь: {order[1]}\n"
        f"📦 Услуга: {service_name}\n"
        f"🔢 Количество: {order[3]}\n"
        f"💰 Сумма: {order[4]} руб.\n"
        f"🔗 Ссылка: {order[5]}"
    )

@dp.callback_query(F.data.startswith("decline_"))
async def decline_order_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id not in ADMINS:
        return
    order_id = call.data.split("_")[1]
    order = await database.get_order(order_id)
    if not order:
        return await call.message.answer("Заказ не найден.")
    if order[6] not in ("NEW", "PENDING"):
        return await call.message.answer("Этот заказ уже обработан другим администратором.")
    await state.update_data(order_id=order_id, order=order)
    await call.message.answer("Введите причину отклонения заказа (одним сообщением):")
    await state.set_state(DeclineReason.waiting_reason)

@dp.message(DeclineReason.waiting_reason)
async def decline_order_reason(message: Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        return await state.clear()
    reason = message.text.strip()
    data = await state.get_data()
    order_id = data['order_id']
    order = data['order']
    await database.update_order_status(order_id, "DECLINED", f"Отклонён: {reason}")
    try:
        await bot.send_message(order[1], f"❌ Ваш заказ №{order_id} отклонён.\nПричина: {reason}")
    except TelegramForbiddenError:
        logging.warning(f"User {order[1]} blocked the bot.")
    except Exception as e:
        logging.error(f"Error sending to user: {e}")
    await message.answer(f"❌ Заказ №{order_id} отклонён.\nПричина: {reason}")
    await state.clear()

# ====== КАЛЬКУЛЯТОР ======
@dp.callback_query(F.data == "calc")
async def calc_menu(call: CallbackQuery):
    await call.answer()
    if await check_ban(call.from_user.id):
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="Подписчики", callback_data="calc_subscribers")
    kb.button(text="Просмотры", callback_data="calc_views")
    kb.button(text="Реакции", callback_data="calc_reactions")
    kb.button(text="◀️ Вернуться назад", callback_data="back_to_main")
    kb.adjust(1)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("Выберите услугу:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("calc_"))
async def calc_choose(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban(call.from_user.id):
        return
    service = call.data.split("_")[1]
    await state.update_data(service=service)
    await call.message.answer("Введите количество:")
    await state.set_state(CalcState.waiting_quantity)

@dp.message(CalcState.waiting_quantity)
async def calc_result(message: Message, state: FSMContext):
    if await check_ban(message.from_user.id):
        return await state.clear()
    if not message.text or not message.text.isdigit():
        return await message.answer("Введите число!")
    quantity = int(message.text)
    data = await state.get_data()
    service = data.get("service")
    if service not in PRICES:
        await state.clear()
        return await message.answer("Ошибка: услуга не найдена. Начните заново.")
    price = quantity * PRICES[service]
    await message.answer(f"💰 Стоимость будет: {price} руб.")
    await state.clear()

# ====== ТЕХ. ПОДДЕРЖКА (просто текст) ======
@dp.callback_query(F.data == "support")
async def support(call: CallbackQuery):
    await call.answer()
    if await check_ban(call.from_user.id):
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Вернуться назад", callback_data="back_to_main")
    await call.message.answer(
        "📞 Связаться с поддержкой:\n\n"
        "Напишите нам в Telegram: @support_username\n"
        "Или на почту: support@example.com",
        reply_markup=kb.as_markup()
    )

# ====== FAQ ======
@dp.callback_query(F.data == "faq")
async def faq(call: CallbackQuery):
    await call.answer()
    if await check_ban(call.from_user.id):
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Вернуться назад", callback_data="back_to_main")
    await call.message.answer(
        """
❓ Частые вопросы:

1. Когда начнётся накрутка?
— После подтверждения оплаты.

2. Есть ли гарантия?
— Да.
        """,
        reply_markup=kb.as_markup()
    )

# ====== КНОПКА НАЗАД ======
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(call: CallbackQuery):
    await call.answer()
    if await check_ban(call.from_user.id):
        return
    await show_main_menu(call.from_user.id, call)

# ====== АДМИН КОМАНДЫ ======
@dp.message(Command("ban"))
async def ban_cmd(message: Message):
    if message.from_user.id not in ADMINS:
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Использование: /ban <user_id>")
    try:
        user_id = int(args[1])
    except ValueError:
        return await message.answer("ID должен быть числом.")
    await database.ban_user(user_id)
    await message.answer(f"Пользователь {user_id} забанен.")

@dp.message(Command("unban"))
async def unban_cmd(message: Message):
    if message.from_user.id not in ADMINS:
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Использование: /unban <user_id>")
    try:
        user_id = int(args[1])
    except ValueError:
        return await message.answer("ID должен быть числом.")
    await database.unban_user(user_id)
    await message.answer(f"Пользователь {user_id} разбанен.")

@dp.message(Command("search"))
async def search_order(message: Message):
    if message.from_user.id not in ADMINS:
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Использование: /search <order_id>")
    order_id = args[1]
    order = await database.get_order(order_id)
    if order:
        await message.answer(str(order))
    else:
        await message.answer("Заказ не найден.")

# ====== RUN ======
async def main():
    await database.init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())