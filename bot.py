import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.exceptions import TelegramForbiddenError
from config import BOT_TOKEN, ADMINS, CARD_DETAILS, CRYPTO_DETAILS
import database

# Настройка логирования
logging.basicConfig(level=logging.INFO)

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


# ====== Состояния ======

class OrderState(StatesGroup):
    waiting_quantity = State()
    waiting_link = State()


class CalcState(StatesGroup):
    waiting_quantity = State()


class TicketState(StatesGroup):
    waiting_text = State()


# ====== Цены ======

PRICES = {
    "subscribers": 0.02,
    "views": 0.01,
    "reactions": 0.01
}


# ====== Проверка бана ======
async def check_ban(user_id: int) -> bool:
    banned = await database.is_banned(user_id)
    if banned:
        await bot.send_message(user_id, "❌ Вы заблокированы.")
        return True
    return False


# ====== /start ======

@dp.message(Command("start"))
async def start_handler(message: Message):
    await database.add_user(message.from_user.id)

    if await check_ban(message.from_user.id):
        return

    kb = InlineKeyboardBuilder()
    kb.button(text="🛒 Заказать накрутку", callback_data="order")
    kb.button(text="🧮 Калькулятор", callback_data="calc")
    kb.button(text="🛠 Тех. Поддержка", callback_data="support")
    kb.button(text="❓ Частые вопросы", callback_data="faq")
    kb.adjust(1)

    # Попытка отправить фото, если файла нет – только текст
    try:
        photo = FSInputFile("photo.jpg")
        await message.answer_photo(
            photo,
            caption="Добро пожаловать в наш шоп 🚀",
            reply_markup=kb.as_markup()
        )
    except FileNotFoundError:
        await message.answer(
            "Добро пожаловать в наш шоп 🚀",
            reply_markup=kb.as_markup()
        )


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
    kb.adjust(1)
    # Удаляем старое сообщение (с фото) и отправляем новое текстовое
    try:
        await call.message.delete()
    except Exception:
        pass  # если не удалось удалить (например, слишком старое) — игнорируем
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
    # Простейшая проверка ссылки
    if not link.startswith(("http://", "https://")):
        return await message.answer("Пожалуйста, отправьте корректную ссылку, начинающуюся с http:// или https://")

    data = await state.get_data()

    try:
        order_id = await database.create_order(
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

    # Формируем реквизиты, только если они не пустые
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

    try:
        order_id = int(call.data.split("_")[1])
    except ValueError:
        return await call.message.answer("Некорректный номер заказа.")

    # Проверим, не обработан ли уже заказ
    order = await database.get_order(order_id)
    if not order:
        return await call.message.answer("Заказ не найден.")
    if order[3] not in ("NEW", "PENDING"):  # предполагаем, что статус хранится в 4-м столбце
        return await call.message.answer("Этот заказ уже обработан.")

    await call.message.answer("⏳ Заказ обрабатывается...")

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Принять", callback_data=f"accept_{order_id}")
    kb.button(text="❌ Отклонить", callback_data=f"decline_{order_id}")

    for admin in ADMINS:
        try:
            await bot.send_message(
                admin,
                f"#НОВЫЙ_ЗАКАЗ\nID: {order_id}",
                reply_markup=kb.as_markup()
            )
        except Exception as e:
            logging.error(f"Failed to send to admin {admin}: {e}")


@dp.callback_query(F.data.startswith("accept_"))
async def accept_order(call: CallbackQuery):
    await call.answer()
    if call.from_user.id not in ADMINS:
        return

    try:
        order_id = int(call.data.split("_")[1])
    except ValueError:
        return await call.message.answer("Некорректный номер заказа.")

    order = await database.get_order(order_id)
    if not order:
        return await call.message.answer("Заказ не найден.")

    # Обновляем статус
    await database.update_order_status(order_id, "ACCEPTED", "Принят")

    # Убираем кнопки у админа
    await call.message.edit_text(call.message.text, reply_markup=None)

    # Уведомляем пользователя
    try:
        await bot.send_message(order[1], "✅ Ваш заказ принят!")
    except TelegramForbiddenError:
        logging.warning(f"User {order[1]} blocked the bot.")
    except Exception as e:
        logging.error(f"Error sending to user: {e}")

    await call.message.answer("Заказ подтверждён.")


@dp.callback_query(F.data.startswith("decline_"))
async def decline_order(call: CallbackQuery):
    await call.answer()
    if call.from_user.id not in ADMINS:
        return

    try:
        order_id = int(call.data.split("_")[1])
    except ValueError:
        return await call.message.answer("Некорректный номер заказа.")

    order = await database.get_order(order_id)
    if not order:
        return await call.message.answer("Заказ не найден.")

    await database.update_order_status(order_id, "DECLINED", "Отклонён")

    # Убираем кнопки
    await call.message.edit_text(call.message.text, reply_markup=None)

    try:
        await bot.send_message(order[1], "❌ Ваш заказ отклонён.")
    except TelegramForbiddenError:
        logging.warning(f"User {order[1]} blocked the bot.")
    except Exception as e:
        logging.error(f"Error sending to user: {e}")

    await call.message.answer("Заказ отклонён.")


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


# ====== ТИКЕТЫ ======

@dp.callback_query(F.data == "support")
async def support(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban(call.from_user.id):
        return
    await call.message.answer("Опишите проблему одним сообщением:")
    await state.set_state(TicketState.waiting_text)


@dp.message(TicketState.waiting_text)
async def send_ticket(message: Message, state: FSMContext):
    if await check_ban(message.from_user.id):
        return await state.clear()

    await state.update_data(text=message.text)

    kb = InlineKeyboardBuilder()
    kb.button(text="📨 Отправить тикет", callback_data="send_ticket")
    kb.button(text="❌ Отмена", callback_data="cancel_ticket")
    kb.adjust(1)

    await message.answer("Отправить тикет?", reply_markup=kb.as_markup())


@dp.callback_query(F.data == "send_ticket")
async def ticket_to_admin(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban(call.from_user.id):
        return await state.clear()

    data = await state.get_data()
    text = data.get("text", "Пустое сообщение")

    for admin in ADMINS:
        try:
            await bot.send_message(admin, f"#ТИКЕТ от {call.from_user.id}\n{text}")
        except Exception as e:
            logging.error(f"Failed to send ticket to admin {admin}: {e}")

    # Убираем кнопки
    await call.message.edit_text("✅ Тикет отправлен.", reply_markup=None)
    await state.clear()


@dp.callback_query(F.data == "cancel_ticket")
async def cancel_ticket(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    await call.message.edit_text("Отменено.", reply_markup=None)


# ====== FAQ ======

@dp.callback_query(F.data == "faq")
async def faq(call: CallbackQuery):
    await call.answer()
    if await check_ban(call.from_user.id):
        return
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("""
❓ Частые вопросы:

1. Когда начнётся накрутка?
— После подтверждения оплаты.

2. Есть ли гарантия?
— Да.
""")


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
    try:
        order_id = int(args[1])
    except ValueError:
        return await message.answer("ID заказа должен быть числом.")
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