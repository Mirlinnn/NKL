import asyncio
import logging
import random
import string
import aiohttp
import json
import uuid
import base64
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.exceptions import TelegramForbiddenError
from config import (
    BOT_TOKEN, ADMINS as STATIC_ADMINS,
    YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, YOOKASSA_RETURN_URL
)
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

class BroadcastState(StatesGroup):
    waiting_message = State()

class PaymentState(StatesGroup):
    waiting_for_payment = State()

# ====== Цены ======
PRICES = {
    "subscribers": 0.02,
    "views": 0.01,
    "reactions": 0.01
}

# ====== Генерация ID заказа ======
def generate_order_id(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# ====== Проверка бана и соглашения ======
async def check_ban_and_terms(user_id: int) -> bool:
    banned = await database.is_banned(user_id)
    if banned:
        await bot.send_message(user_id, "❌ Вы заблокированы.")
        return True

    if not await database.has_accepted_terms(user_id):
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Принять договор оферты и политику конфиденциальности", callback_data="accept_terms")
        await bot.send_message(
            user_id,
            "Для использования бота необходимо принять договор оферты и политику конфиденциальности.\n\n"
            "[Договор оферты](https://t.me/your_offer_link)\n"
            "[Пользовательское соглашение](https://t.me/your_terms_link)",
            reply_markup=kb.as_markup(),
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        return True
    return False

# ====== Принятие соглашения ======
@dp.callback_query(F.data == "accept_terms")
async def accept_terms(call: CallbackQuery):
    await call.answer()
    await database.accept_terms(call.from_user.id)
    await call.message.edit_text("✅ Вы приняли договор оферты и политику конфиденциальности. Теперь вы можете пользоваться ботом.")
    await show_main_menu(call.from_user.id)

# ====== ГЛАВНОЕ МЕНЮ ======
async def show_main_menu(chat_id: int):
    keyboard = [
        [InlineKeyboardButton(text="🛒 Заказать накрутку", callback_data="order")],
        [InlineKeyboardButton(text="🧮 Калькулятор", callback_data="calc")],
        [InlineKeyboardButton(text="🛠 Тех. Поддержка", callback_data="support")],
        [InlineKeyboardButton(text="❓ Частые вопросы", callback_data="faq")]
    ]

    reply_markup = {
        "inline_keyboard": [
            [
                {
                    "text": btn.text,
                    "callback_data": btn.callback_data,
                } for btn in row
            ] for row in keyboard
        ]
    }

    text = """
<b>Приветствую!</b> ✈️
<b>Добро пожаловать в бота для накрутки статистики пользователей, просмотров и реакций

</b><blockquote>👤 <b>Тех.поддержка: @support_username
</b>📈 <b>Наш канал: @channel_username</b></blockquote>

<a href="https://t.me/your_offer_link">Договор оферты</a> • <a href="https://t.me/your_terms_link">Пользовательское соглашение</a>
    """

    async with aiohttp.ClientSession() as session:
        try:
            photo = FSInputFile("photo.jpg")
            form_data = aiohttp.FormData()
            form_data.add_field('chat_id', str(chat_id))
            form_data.add_field('caption', text)
            form_data.add_field('parse_mode', 'HTML')
            form_data.add_field('reply_markup', json.dumps(reply_markup))
            form_data.add_field('photo', open('photo.jpg', 'rb'), filename='photo.jpg')
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            async with session.post(url, data=form_data) as resp:
                if resp.status != 200:
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                    payload = {
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                        "reply_markup": reply_markup,
                        "disable_web_page_preview": True
                    }
                    await session.post(url, json=payload)
        except FileNotFoundError:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
                "disable_web_page_preview": True
            }
            await session.post(url, json=payload)

# ====== /start ======
@dp.message(Command("start"))
async def start_handler(message: Message):
    await database.add_user(message.from_user.id)
    if await check_ban_and_terms(message.from_user.id):
        return
    await show_main_menu(message.chat.id)

# ====== ЗАКАЗ ======
@dp.callback_query(F.data == "order")
async def order_menu(call: CallbackQuery):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return

    keyboard = [
        [InlineKeyboardButton(text="Подписчики", callback_data="subscribers")],
        [InlineKeyboardButton(text="Просмотры", callback_data="views")],
        [InlineKeyboardButton(text="Реакции", callback_data="reactions")],
        [InlineKeyboardButton(text="◀️ Вернуться назад", callback_data="back_to_main")]
    ]

    reply_markup = {
        "inline_keyboard": [
            [
                {
                    "text": btn.text,
                    "callback_data": btn.callback_data,
                } for btn in row
            ] for row in keyboard
        ]
    }

    text = """
<b>Заказать услугу</b><tg-emoji emoji-id="5870695289714643076">👤</tg-emoji><b>

Выберите услугу из списка ниже.</b><tg-emoji emoji-id="5870633910337015697">✅</tg-emoji>
<a href="https://t.me/shiitead">Курс для каждой услуги</a>
    """

    async with aiohttp.ClientSession() as session:
        try:
            await call.message.delete()
        except Exception:
            pass

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": call.from_user.id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": reply_markup,
            "disable_web_page_preview": True
        }

        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                logging.error(f"Failed to send order menu via direct API: {await resp.text()}")
                kb = InlineKeyboardBuilder()
                kb.button(text="Подписчики", callback_data="subscribers")
                kb.button(text="Просмотры", callback_data="views")
                kb.button(text="Реакции", callback_data="reactions")
                kb.button(text="◀️ Вернуться назад", callback_data="back_to_main")
                kb.adjust(1)
                await call.message.answer(
                    text.replace("<tg-emoji", "<!-- tg-emoji").replace("</tg-emoji>", "-->"),
                    reply_markup=kb.as_markup(),
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )

@dp.callback_query(F.data.in_(["subscribers", "views", "reactions"]))
async def choose_service(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return

    service = call.data
    await state.update_data(service=service)

    if service == "subscribers":
        text = """
<tg-emoji emoji-id="5870729082517328189">📊</tg-emoji><b>Тип услуги: Подписчики</b><tg-emoji emoji-id="5870994129244131212">👤</tg-emoji><b>
Выберете количество подписчиков: от 1 до 100.000 человек
</b><a href="https://t.me/ineedforyou/5">Курс для каждой услуги</a>
        """
    elif service == "reactions":
        text = """
<tg-emoji emoji-id="5870729082517328189">📊</tg-emoji><b>Тип услуги: Реакции</b><tg-emoji emoji-id="5870994129244131212">👤</tg-emoji><b>
Выберете количество подписчиков: от 1 до 1.00.000 человек
</b><a href="https://t.me/ineedforyou/5">Курс для каждой услуги</a>
        """
    else:  # views
        text = """
<tg-emoji emoji-id="5870729082517328189">📊</tg-emoji><b>Тип услуги: Просмотры</b><tg-emoji emoji-id="5870994129244131212">👤</tg-emoji><b>
Выберете количество подписчиков: от 1 до 100.000 человек
</b><a href="https://t.me/ineedforyou/5">Курс для каждой услуги</a>
        """

    async with aiohttp.ClientSession() as session:
        try:
            await call.message.delete()
        except Exception:
            pass

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": call.from_user.id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                logging.error(f"Failed to send service choice message via direct API: {await resp.text()}")
                await call.message.answer(
                    text.replace("<tg-emoji", "<!-- tg-emoji").replace("</tg-emoji>", "-->"),
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )

    await state.set_state(OrderState.waiting_quantity)

@dp.message(OrderState.waiting_quantity)
async def get_quantity(message: Message, state: FSMContext):
    if await check_ban_and_terms(message.from_user.id):
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

# ====== ФУНКЦИЯ ПРЯМОГО ЗАПРОСА К ЮKASSA ======
async def create_yookassa_payment(amount: float, description: str, order_id: str, user_id: int):
    auth = base64.b64encode(f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json",
        "Idempotence-Key": str(uuid.uuid4())
    }
    data = {
        "amount": {
            "value": f"{amount:.2f}",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": YOOKASSA_RETURN_URL
        },
        "capture": True,
        "description": description,
        "metadata": {
            "order_id": order_id,
            "user_id": user_id
        }
    }

    async with aiohttp.ClientSession() as session:
        async with session.post("https://api.yookassa.ru/v3/payments", headers=headers, json=data) as resp:
            response_text = await resp.text()
            logging.info(f"YooKassa response status: {resp.status}")
            logging.info(f"YooKassa response body: {response_text}")
            if resp.status not in (200, 201):
                raise Exception(f"YooKassa error {resp.status}: {response_text}")
            return json.loads(response_text)

# ====== ОБРАБОТКА ССЫЛКИ И СОЗДАНИЕ ПЛАТЕЖА (исправленная версия) ======
@dp.message(OrderState.waiting_link)
async def get_link(message: Message, state: FSMContext):
    if await check_ban_and_terms(message.from_user.id):
        return await state.clear()
    link = message.text.strip()
    if not link.startswith(("http://", "https://")):
        return await message.answer("Пожалуйста, отправьте корректную ссылку, начинающуюся с http:// или https://")
    data = await state.get_data()
    order_id = generate_order_id()
    service = data['service']
    quantity = data['quantity']
    price = data['price']

    # Сначала создаём платёж, чтобы получить payment_id
    try:
        payment_data = await create_yookassa_payment(
            amount=price,
            description=f"Заказ {order_id}: {service} x{quantity}",
            order_id=order_id,
            user_id=message.from_user.id
        )

        payment_id = payment_data.get('id')
        confirmation_url = payment_data.get('confirmation', {}).get('confirmation_url')

        if not payment_id or not confirmation_url:
            raise Exception("Missing payment_id or confirmation_url in response")

        logging.info(f"Payment ID from YooKassa: {payment_id}")

        # Теперь сохраняем заказ в БД с уже известным payment_id
        await database.create_order_with_payment(
            order_id=order_id,
            user_id=message.from_user.id,
            service=service,
            quantity=quantity,
            price=price,
            link=link,
            payment_id=payment_id,
            status="PENDING"
        )
        logging.info(f"Order {order_id} created with payment_id {payment_id}")

        # Проверяем, что сохранилось
        order_check = await database.get_order(order_id)
        if order_check:
            logging.info(f"Full order record: {order_check}")
            # Найдём индекс payment_id по заголовкам (но пока просто выведем)
            # Ожидаем, что payment_id где-то в кортеже. По нашей функции create_order_with_payment мы вставляем payment_id как 8-й параметр.
            saved_payment_id = order_check[8] if len(order_check) > 8 else None
            logging.info(f"Saved payment_id in DB: {saved_payment_id}")
        else:
            logging.error(f"Order {order_id} not found after creation!")

        # Отправляем пользователю сообщение с кнопкой оплаты
        kb = InlineKeyboardBuilder()
        kb.button(text="💳 Оплатить на сайте", url=confirmation_url)
        kb.adjust(1)

        await message.answer(
            f"✅ Заказ №{order_id} создан!\n\n"
            f"Услуга: {service}\nКоличество: {quantity}\nСумма: {price:.2f} руб.\n\n"
            f"Для оплаты перейдите по ссылке ниже. После успешной оплаты заказ будет подтверждён автоматически.",
            reply_markup=kb.as_markup(),
            disable_web_page_preview=True
        )
        await state.set_state(PaymentState.waiting_for_payment)

    except Exception as e:
        logging.error(f"YooKassa error: {e}")
        await message.answer("Не удалось создать платёж. Попробуйте позже.")
        await state.clear()

# ====== ФУНКЦИЯ ПРОВЕРКИ СТАТУСА ПЛАТЕЖА ======
async def check_payment_status(payment_id: str):
    auth = base64.b64encode(f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.yookassa.ru/v3/payments/{payment_id}", headers=headers) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return data.get('status')

# ====== ФОНОВАЯ ЗАДАЧА ДЛЯ ПРОВЕРКИ СТАТУСОВ ======
async def check_payments_status():
    while True:
        try:
            pending_orders = await database.get_pending_orders()
            if pending_orders:
                logging.info(f"Checking {len(pending_orders)} pending orders...")
            for order in pending_orders:
                order_id = order[0]
                payment_id = order[8]  # предполагаем, что payment_id на 8-й позиции
                if not payment_id:
                    logging.warning(f"Order {order_id} has no payment_id, skipping.")
                    continue

                logging.info(f"Checking order {order_id}, payment_id: {payment_id}")
                try:
                    status = await check_payment_status(payment_id)
                    if status is None:
                        logging.warning(f"Payment {payment_id} not found or error")
                        continue
                    logging.info(f"Payment {payment_id} status: {status}")
                    if status == 'succeeded':
                        await database.update_order_status(order_id, "PAID", "Оплачено через ЮKassa (авто)")

                        user_id = order[1]
                        try:
                            await bot.send_message(
                                user_id,
                                f"✅ Ваш заказ №{order_id} оплачен! Мы начали выполнение.",
                                disable_web_page_preview=True
                            )
                            logging.info(f"User {user_id} notified about payment for order {order_id}")
                        except Exception as e:
                            logging.error(f"Failed to notify user {user_id}: {e}")

                        admins = await database.get_all_admins()
                        for admin in admins:
                            try:
                                await bot.send_message(
                                    admin,
                                    f"💰 Автоматически подтверждена оплата заказа №{order_id} от пользователя {user_id}."
                                )
                            except Exception as e:
                                logging.error(f"Failed to notify admin {admin}: {e}")

                        logging.info(f"Order {order_id} marked as PAID via polling")
                except Exception as e:
                    logging.error(f"Error checking payment {payment_id} for order {order_id}: {e}")
        except Exception as e:
            logging.error(f"Error in payment status checker: {e}")

        await asyncio.sleep(30)

# ====== ДИАГНОСТИЧЕСКАЯ КОМАНДА ДЛЯ АДМИНОВ ======
@dp.message(Command("fixdb"))
async def fixdb_command(message: Message):
    if not await database.is_admin(message.from_user.id):
        return
    # Покажем структуру таблицы orders
    try:
        async with aiosqlite.connect(database.DB_PATH) as db:
            cursor = await db.execute("PRAGMA table_info(orders)")
            rows = await cursor.fetchall()
            info = "Структура таблицы orders:\n"
            for row in rows:
                info += f"{row[0]}: {row[1]} ({row[2]})\n"
            await message.answer(info)
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

# ====== ОСТАЛЬНЫЕ ОБРАБОТЧИКИ (без изменений, но для краткости опущены) ======
# ... (все остальные хендлеры из предыдущей версии остаются без изменений)
# Для экономии места я не копирую их снова, но вы должны оставить все остальные обработчики
# (accept_*, decline_*, calc, support, faq, back_to_main, админские команды) такими же, как в последней версии.
# Если нужно, я могу предоставить полный файл целиком, но здесь я показываю ключевые изменения.

# ====== RUN ======
async def main():
    await database.init_db()
    for admin_id in STATIC_ADMINS:
        await database.add_admin(admin_id)

    asyncio.create_task(check_payments_status())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())