import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from config import BOT_TOKEN, ADMINS, CARD_DETAILS, CRYPTO_DETAILS
import database

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


# ====== /start ======

@dp.message(Command("start"))
async def start_handler(message: Message):
    await database.add_user(message.from_user.id)

    if await database.is_banned(message.from_user.id):
        return await message.answer("❌ Вы заблокированы.")

    kb = InlineKeyboardBuilder()
    kb.button(text="🛒 Заказать накрутку", callback_data="order")
    kb.button(text="🧮 Калькулятор", callback_data="calc")
    kb.button(text="🛠 Тех. Поддержка", callback_data="support")
    kb.button(text="❓ Частые вопросы", callback_data="faq")
    kb.adjust(1)

    photo = FSInputFile("photo.jpg")  # добавь свою картинку

    await message.answer_photo(
        photo,
        caption="Добро пожаловать в наш шоп 🚀",
        reply_markup=kb.as_markup()
    )


# ====== ЗАКАЗ ======

@dp.callback_query(F.data == "order")
async def order_menu(call: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="Подписчики", callback_data="subscribers")
    kb.button(text="Просмотры", callback_data="views")
    kb.button(text="Реакции", callback_data="reactions")
    kb.adjust(1)
    if call.message.photo:
    await call.message.edit_caption(
        "Выберите услугу:",
        reply_markup=kb.as_markup()
    )
else:
    await call.message.edit_text(
        "Выберите услугу:",
        reply_markup=kb.as_markup()
    )

@dp.callback_query(F.data.in_(["subscribers", "views", "reactions"]))
async def choose_service(call: CallbackQuery, state: FSMContext):
    await state.update_data(service=call.data)
    await call.message.answer("Введите количество:")
    await state.set_state(OrderState.waiting_quantity)


@dp.message(OrderState.waiting_quantity)
async def get_quantity(message: Message, state: FSMContext):
    if not message.text.isdigit():
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
    data = await state.get_data()

    order_id = await database.create_order(
        message.from_user.id,
        data["service"],
        data["quantity"],
        data["price"],
        message.text
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Проверить платёж", callback_data=f"check_{order_id}")

    await message.answer(
        f"""
📦 Заказ №{order_id}

Услуга: {data['service']}
Кол-во: {data['quantity']}
Цена: {data['price']} руб
Ссылка: {message.text}

{CARD_DETAILS}
{CRYPTO_DETAILS}
""",
        reply_markup=kb.as_markup()
    )

    await state.clear()


@dp.callback_query(F.data.startswith("check_"))
async def check_payment(call: CallbackQuery):
    order_id = int(call.data.split("_")[1])
    await call.message.answer("⏳ Заказ обрабатывается...")

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Принять", callback_data=f"accept_{order_id}")
    kb.button(text="❌ Отклонить", callback_data=f"decline_{order_id}")

    for admin in ADMINS:
        await bot.send_message(
            admin,
            f"#НОВЫЙ_ЗАКАЗ\nID: {order_id}",
            reply_markup=kb.as_markup()
        )


@dp.callback_query(F.data.startswith("accept_"))
async def accept_order(call: CallbackQuery):
    order_id = int(call.data.split("_")[1])
    order = await database.get_order(order_id)

    await database.update_order_status(order_id, "ACCEPTED", "Принят")
    await bot.send_message(order[1], "✅ Ваш заказ принят!")
    await call.message.answer("Заказ подтверждён.")


@dp.callback_query(F.data.startswith("decline_"))
async def decline_order(call: CallbackQuery):
    order_id = int(call.data.split("_")[1])
    order = await database.get_order(order_id)

    await database.update_order_status(order_id, "DECLINED", "Отклонён")
    await bot.send_message(order[1], "❌ Ваш заказ отклонён.")
    await call.message.answer("Заказ отклонён.")


# ====== КАЛЬКУЛЯТОР ======

@dp.callback_query(F.data == "calc")
async def calc_menu(call: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="Подписчики", callback_data="calc_subscribers")
    kb.button(text="Просмотры", callback_data="calc_views")
    kb.button(text="Реакции", callback_data="calc_reactions")
    kb.adjust(1)

    await call.message.edit_text("Выберите услугу:", reply_markup=kb.as_markup())


@dp.callback_query(F.data.startswith("calc_"))
async def calc_choose(call: CallbackQuery, state: FSMContext):
    service = call.data.split("_")[1]
    await state.update_data(service=service)
    await call.message.answer("Введите количество:")
    await state.set_state(CalcState.waiting_quantity)


@dp.message(CalcState.waiting_quantity)
async def calc_result(message: Message, state: FSMContext):
    quantity = int(message.text)
    data = await state.get_data()
    price = quantity * PRICES[data["service"]]

    await message.answer(f"💰 Стоимость будет: {price} руб.")
    await state.clear()


# ====== ТИКЕТЫ ======

@dp.callback_query(F.data == "support")
async def support(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Опишите проблему одним сообщением:")
    await state.set_state(TicketState.waiting_text)


@dp.message(TicketState.waiting_text)
async def send_ticket(message: Message, state: FSMContext):
    kb = InlineKeyboardBuilder()
    kb.button(text="📨 Отправить тикет", callback_data="send_ticket")

    await state.update_data(text=message.text)
    await message.answer("Отправить тикет?", reply_markup=kb.as_markup())


@dp.callback_query(F.data == "send_ticket")
async def ticket_to_admin(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    for admin in ADMINS:
        await bot.send_message(admin, f"#ТИКЕТ\n{data['text']}")

    await call.message.answer("✅ Тикет отправлен.")
    await state.clear()


# ====== FAQ ======

@dp.callback_query(F.data == "faq")
async def faq(call: CallbackQuery):
    await call.message.edit_text("""
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
    user_id = int(message.text.split()[1])
    await database.ban_user(user_id)
    await message.answer("Пользователь забанен.")


@dp.message(Command("unban"))
async def unban_cmd(message: Message):
    if message.from_user.id not in ADMINS:
        return
    user_id = int(message.text.split()[1])
    await database.unban_user(user_id)
    await message.answer("Пользователь разбанен.")


@dp.message(Command("search"))
async def search_order(message: Message):
    if message.from_user.id not in ADMINS:
        return
    order_id = int(message.text.split()[1])
    order = await database.get_order(order_id)
    await message.answer(str(order))


# ====== RUN ======

async def main():
    await database.init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
