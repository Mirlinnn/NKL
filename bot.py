import asyncio
import logging
import random
import string
import aiohttp
import json
import uuid
import base64
import hashlib
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.exceptions import TelegramForbiddenError
from config import (
    BOT_TOKEN, OWNER_ID, ADMINS as STATIC_ADMINS,
    YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, YOOKASSA_RETURN_URL,
    HELEKET_MERCHANT_ID, HELEKET_API_KEY, HELEKET_API_URL, HELEKET_RETURN_URL
)
import database

import aiosqlite

logging.basicConfig(level=logging.INFO)
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ====== Состояния ======
class OrderState(StatesGroup):
    waiting_quantity = State()
    waiting_link = State()

class SubscribersDuration(StatesGroup):
    waiting_duration = State()

class ReactionsType(StatesGroup):
    waiting_reaction_type = State()
    waiting_reaction_emoji = State()

class BalanceTopup(StatesGroup):
    waiting_amount = State()
    waiting_method = State()

class CalcState(StatesGroup):
    waiting_quantity = State()
    waiting_reaction_type = State()

class DeclineReason(StatesGroup):
    waiting_reason = State()

class BroadcastState(StatesGroup):
    waiting_message = State()

class StopOrderReason(StatesGroup):
    waiting_reason = State()

class BanReason(StatesGroup):
    waiting_reason = State()

# ====== Цены и параметры ======
VIEWS_PRICE = 1.0
STARTS_PRICE = 0.03  # цена за старт

REACTION_PRICES = {
    "positive": 1/150,
    "negative": 1/150,
    "emoji_list": 0.01
}

SUBSCRIBER_PRICES = {
    "day": 1.0,
    "3days": 2.5,
    "7days": 3.0,
    "30days": 5.0,
    "90days": 7.0,
    "forever": 10.0
}

SUBSCRIBER_MINIMUMS = {
    "day": 100,
    "3days": 40,
    "7days": 35,
    "30days": 20,
    "90days": 15,
    "forever": 10
}

SUBSCRIBER_DURATIONS = {
    "day": "1 день",
    "3days": "3 дня",
    "7days": "7 дней",
    "30days": "30 дней",
    "90days": "90 дней",
    "forever": "Навсегда"
}

REACTION_TYPES = {
    "positive": "Позитивные",
    "negative": "Негативные",
    "emoji_list": "Эмодзи из списка"
}

EMOJI_LIST = ["👍", "🤡", "💩", "❤️", "🤝", "🖕", "👀", "🍌", "👻", "🕊", "🌲", "🗿", "🍾", "👌", "🤬"]

MIN_TOPUP_YOOKASSA = 1.0
MIN_TOPUP_HELEKET = 5.0

STARTS_MIN = 10

# ====== Генерация ID заказа ======
def generate_order_id(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# ====== Проверка активности бота ======
async def is_bot_available(user_id: int) -> bool:
    if user_id == OWNER_ID or await database.is_admin(user_id):
        return True
    if await database.is_banned(user_id):
        return False
    return await database.is_bot_active()

# ====== Проверка бана и соглашения ======
async def check_ban_and_terms(user_id: int) -> bool:
    if not await is_bot_available(user_id):
        bot_status = await database.get_bot_status()
        if bot_status.get('active') == '0':
            reason = bot_status.get('reason', 'Бот временно недоступен.')
            await bot.send_message(user_id, f"❌ {reason}")
        else:
            await bot.send_message(user_id, "❌ Бот временно недоступен. Попробуйте позже.")
        return True

    ban_info = await database.get_ban_info(user_id)
    if ban_info and ban_info[0] == 1:
        ban_reason = ban_info[3] or "Не указана"
        await bot.send_message(user_id, f"❌ Вы заблокированы.\nПричина: {ban_reason}")
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
    balance = await database.get_balance(chat_id)
    keyboard = [
        [InlineKeyboardButton(text="🛒 Заказать накрутку", callback_data="order")],
        [InlineKeyboardButton(text="🧮 Калькулятор", callback_data="calc")],
        [InlineKeyboardButton(text="💰 Баланс", callback_data="balance")],
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

    text = f"""
<b>Приветствую!</b> <tg-emoji emoji-id="5877700484453634587">✈️</tg-emoji>
<b>Добро пожаловать в бота для накрутки статистики пользователей, просмотров и реакций

</b><blockquote><tg-emoji emoji-id="5870994129244131212">👤</tg-emoji> <b>Тех.поддержка: </b>@nBoost_supports<b>
</b><tg-emoji emoji-id="5870995486453796729">📊</tg-emoji> <b>Наш канал: </b>@channel_username</blockquote>
<a href="https://t.me/your_offer_link">Договор оферты</a> • <a href="https://t.me/your_terms_link">Пользовательское соглашение</a>

<b>💰 Ваш баланс: {balance:.2f} руб.</b>
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

# ====== БАЛАНС ======
@dp.callback_query(F.data == "balance")
async def balance_menu(call: CallbackQuery):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    balance = await database.get_balance(call.from_user.id)
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Пополнить картой (от 1₽)", callback_data="topup_yookassa")
    kb.button(text="₿ Пополнить криптовалютой (от 5₽)", callback_data="topup_heleket")
    kb.button(text="📜 История пополнений", callback_data="topup_history")
    kb.button(text="◀️ Назад", callback_data="back_to_main")
    kb.adjust(1)

    await call.message.edit_text(
        f"💰 <b>Ваш баланс: {balance:.2f} руб.</b>\n\n"
        "Выберите действие:",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "topup_yookassa")
async def topup_yookassa_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(method="yookassa")
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Отмена", callback_data="balance")
    await call.message.edit_text(
        f"Введите сумму пополнения (от {MIN_TOPUP_YOOKASSA:.2f} руб.):",
        reply_markup=kb.as_markup()
    )
    await state.set_state(BalanceTopup.waiting_amount)

@dp.callback_query(F.data == "topup_heleket")
async def topup_heleket_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(method="heleket")
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Отмена", callback_data="balance")
    await call.message.edit_text(
        f"Введите сумму пополнения (от {MIN_TOPUP_HELEKET:.2f} руб.):",
        reply_markup=kb.as_markup()
    )
    await state.set_state(BalanceTopup.waiting_amount)

@dp.callback_query(F.data == "topup_history")
async def topup_history(call: CallbackQuery):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    transactions = await database.get_transactions(call.from_user.id, 10)
    if not transactions:
        text = "📜 История пополнений пуста."
    else:
        text = "📜 <b>Последние пополнения:</b>\n"
        for tx in transactions:
            status_emoji = "✅" if tx[4] == "success" else "❌"
            text += f"{status_emoji} {tx[6][:10]} +{tx[2]:.2f} руб. ({tx[3]})\n"
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Назад", callback_data="balance")
    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.message(BalanceTopup.waiting_amount)
async def topup_amount(message: Message, state: FSMContext):
    if await check_ban_and_terms(message.from_user.id):
        return await state.clear()
    if not message.text or not message.text.replace('.', '').isdigit():
        return await message.answer("Введите число (например, 100.50).")
    amount = float(message.text)
    data = await state.get_data()
    method = data.get("method")
    if method == "yookassa" and amount < MIN_TOPUP_YOOKASSA:
        return await message.answer(f"Минимальная сумма пополнения: {MIN_TOPUP_YOOKASSA:.2f} руб.")
    if method == "heleket" and amount < MIN_TOPUP_HELEKET:
        return await message.answer(f"Минимальная сумма пополнения: {MIN_TOPUP_HELEKET:.2f} руб.")

    await state.update_data(amount=amount)
    if method == "yookassa":
        await create_yookassa_topup(message, state, amount)
    else:
        await create_heleket_topup(message, state, amount)

async def create_yookassa_topup(message: Message, state: FSMContext, amount: float):
    try:
        payment_data = await create_yookassa_payment(
            amount=amount,
            description=f"Пополнение баланса пользователя {message.from_user.id}",
            order_id=f"topup_{message.from_user.id}_{uuid.uuid4().hex[:8]}",
            user_id=message.from_user.id
        )
        payment_id = payment_data.get('id')
        confirmation_url = payment_data.get('confirmation', {}).get('confirmation_url')
        if not payment_id or not confirmation_url:
            raise Exception("Missing payment data")
        await database.add_transaction(message.from_user.id, amount, "yookassa", "pending", payment_id)
        kb = InlineKeyboardBuilder()
        kb.button(text="💳 Оплатить картой", url=confirmation_url)
        kb.button(text="✅ Проверить оплату", callback_data=f"check_topup_{payment_id}")
        await message.answer(
            f"<emoji document_id=\"5427009714745517609\">✅</emoji><b>Создан счет на {amount:.2f} руб.</b>\nПосле оплаты нажмите на кнопку \"Проверить оплату\"",
            reply_markup=kb.as_markup(),
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        await state.clear()
    except Exception as e:
        logging.error(f"Topup error: {e}")
        await message.answer("Не удалось создать платёж. Попробуйте позже.")
        await state.clear()

async def create_heleket_topup(message: Message, state: FSMContext, amount: float):
    try:
        payment_result = await create_heleket_payment(
            amount=amount,
            order_id=f"topup_{message.from_user.id}_{uuid.uuid4().hex[:8]}",
            description=f"Пополнение баланса",
            user_id=message.from_user.id
        )
        payment_uuid = payment_result.get('uuid')
        payment_url = payment_result.get('url')
        if not payment_uuid or not payment_url:
            raise Exception("Missing payment data")
        await database.add_transaction(message.from_user.id, amount, "heleket", "pending", payment_uuid)
        kb = InlineKeyboardBuilder()
        kb.button(text="₿ Оплатить криптовалютой", url=payment_url)
        kb.button(text="✅ Проверить оплату", callback_data=f"check_topup_{payment_uuid}")
        await message.answer(
            f"<emoji document_id=\"5427009714745517609\">✅</emoji><b>Создан счет на {amount:.2f} руб.</b>\nПосле оплаты нажмите на кнопку \"Проверить оплату\"",
            reply_markup=kb.as_markup(),
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        await state.clear()
    except Exception as e:
        logging.error(f"Heleket topup error: {e}")
        await message.answer("Не удалось создать платёж. Попробуйте позже.")
        await state.clear()

@dp.callback_query(F.data.startswith("check_topup_"))
async def check_topup_callback(call: CallbackQuery):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    payment_id = call.data.split("_")[2]
    async with aiosqlite.connect(database.DB_PATH) as db:
        async with db.execute('SELECT * FROM transactions WHERE payment_id = ?', (payment_id,)) as cursor:
            tx = await cursor.fetchone()
    if not tx:
        await call.message.answer("Транзакция не найдена.")
        return
    if tx[4] == "success":
        await call.message.answer("Этот платёж уже был обработан.")
        return
    if tx[3] == "yookassa":
        status = await check_yookassa_payment(payment_id)
        success_status = 'succeeded'
    else:
        status = await check_heleket_payment(payment_id)
        success_status = 'paid'
    if status == success_status:
        await database.update_balance(tx[1], tx[2])
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute('UPDATE transactions SET status = ? WHERE id = ?', ("success", tx[0]))
            await db.commit()
        await call.message.edit_text(f"✅<b>Принято! Баланс пополнен на {tx[2]:.2f} руб.</b>", reply_markup=None, parse_mode="HTML")
        await call.message.answer("Теперь вы можете заказывать услуги.")
    else:
        await call.message.answer(
            f"<b>❌Платёж не оплачен, попробуйте позже.\nЕсли вы оплатили, но ошибка повторяется, напишите техподдержке бота: </b>@nBoost_supports",
            parse_mode="HTML"
        )

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
        [InlineKeyboardButton(text="Старты", callback_data="starts")],
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
                kb.button(text="Старты", callback_data="starts")
                kb.button(text="◀️ Вернуться назад", callback_data="back_to_main")
                kb.adjust(1)
                await call.message.answer(
                    text.replace("<tg-emoji", "<!-- tg-emoji").replace("</tg-emoji>", "-->"),
                    reply_markup=kb.as_markup(),
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )

@dp.callback_query(F.data == "subscribers")
async def choose_subscribers(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(service="subscribers")

    kb = InlineKeyboardBuilder()
    for key, name in SUBSCRIBER_DURATIONS.items():
        price = SUBSCRIBER_PRICES[key]
        min_q = SUBSCRIBER_MINIMUMS[key]
        kb.button(text=f"{name} - {price}₽ за 100 чел (мин {min_q})", callback_data=f"sub_dur_{key}")
    kb.button(text="◀️ Назад к выбору услуги", callback_data="order")
    kb.adjust(2)

    await call.message.edit_text(
        "<b>Выберите длительность услуги</b><tg-emoji emoji-id=\"5386713103213814186\">❕</tg-emoji>",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(SubscribersDuration.waiting_duration)

@dp.callback_query(F.data == "views")
async def choose_views(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(service="views")
    await call.message.edit_text("Введите количество просмотров (минимум 1):")
    await state.set_state(OrderState.waiting_quantity)

@dp.callback_query(F.data == "reactions")
async def choose_reactions(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(service="reactions")

    kb = InlineKeyboardBuilder()
    for key, name in REACTION_TYPES.items():
        price_per_unit = REACTION_PRICES[key]
        if key == "emoji_list":
            price_text = f"1₽ за 100"
        else:
            price_text = f"1₽ за 150"
        kb.button(text=f"{name} ({price_text})", callback_data=f"react_type_{key}")
    kb.button(text="◀️ Назад к выбору услуги", callback_data="order")
    kb.adjust(2)

    await call.message.edit_text(
        "Выберите тип реакций:",
        reply_markup=kb.as_markup()
    )
    await state.set_state(ReactionsType.waiting_reaction_type)

@dp.callback_query(F.data == "starts")
async def choose_starts(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(service="starts")
    await call.message.edit_text(f"Введите количество стартов (минимум {STARTS_MIN}):")
    await state.set_state(OrderState.waiting_quantity)

# ====== ОБРАБОТЧИКИ ДЛЯ ПОДПИСЧИКОВ ======
@dp.callback_query(SubscribersDuration.waiting_duration, F.data.startswith("sub_dur_"))
async def process_subscribers_duration(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    duration_key = call.data.split("_")[2]
    duration_name = SUBSCRIBER_DURATIONS[duration_key]
    price_per_100 = SUBSCRIBER_PRICES[duration_key]
    min_quantity = SUBSCRIBER_MINIMUMS[duration_key]
    await state.update_data(subtype=duration_name, duration_key=duration_key, price_per_100=price_per_100, min_quantity=min_quantity)
    await call.message.edit_text(
        f"Выбрана длительность: {duration_name}\n"
        f"Цена: {price_per_100}₽ за 100 человек\n"
        f"Минимальное количество: {min_quantity} чел.\n\n"
        "Введите количество подписчиков:"
    )
    await state.set_state(OrderState.waiting_quantity)

# ====== ОБРАБОТЧИКИ ДЛЯ РЕАКЦИЙ ======
@dp.callback_query(ReactionsType.waiting_reaction_type, F.data.startswith("react_type_"))
async def process_reaction_type(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    type_key = call.data.split("_")[2]
    logging.info(f"process_reaction_type received type_key: {type_key}")

    if type_key not in REACTION_TYPES:
        logging.error(f"Unknown reaction type key: {type_key}")
        await call.message.answer("❌ Неизвестный тип реакции. Пожалуйста, выберите снова.")
        kb = InlineKeyboardBuilder()
        for key, name in REACTION_TYPES.items():
            price_per_unit = REACTION_PRICES[key]
            if key == "emoji_list":
                price_text = f"1₽ за 100"
            else:
                price_text = f"1₽ за 150"
            kb.button(text=f"{name} ({price_text})", callback_data=f"react_type_{key}")
        kb.button(text="◀️ Назад к выбору услуги", callback_data="order")
        kb.adjust(2)
        await call.message.edit_text(
            "Выберите тип реакций:",
            reply_markup=kb.as_markup()
        )
        return

    type_name = REACTION_TYPES[type_key]
    await state.update_data(reaction_type_key=type_key, reaction_type_name=type_name)

    if type_key == "emoji_list":
        kb = InlineKeyboardBuilder()
        for emoji in EMOJI_LIST:
            kb.button(text=emoji, callback_data=f"react_emoji_{emoji}")
        kb.button(text="◀️ Назад к типам реакций", callback_data="reactions")
        kb.adjust(4)
        await call.message.edit_text(
            "Выберите эмодзи:",
            reply_markup=kb.as_markup()
        )
        await state.set_state(ReactionsType.waiting_reaction_emoji)
    else:
        await call.message.edit_text("Введите количество реакций (минимум 1):")
        await state.set_state(OrderState.waiting_quantity)

@dp.callback_query(ReactionsType.waiting_reaction_emoji, F.data.startswith("react_emoji_"))
async def process_reaction_emoji(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    emoji = call.data.split("_")[2]
    logging.info(f"Reaction emoji selected: {emoji}")
    await state.update_data(selected_emoji=emoji)
    await call.message.edit_text("Введите количество реакций (минимум 1):")
    await state.set_state(OrderState.waiting_quantity)

# ====== ВВОД КОЛИЧЕСТВА ======
@dp.message(OrderState.waiting_quantity)
async def get_quantity(message: Message, state: FSMContext):
    if await check_ban_and_terms(message.from_user.id):
        return await state.clear()
    if not message.text or not message.text.isdigit():
        return await message.answer("Введите число!")

    quantity = int(message.text)
    data = await state.get_data()
    service = data["service"]

    if service == "subscribers":
        min_q = data.get("min_quantity", 100)
        if quantity < min_q:
            return await message.answer(f"Минимальное количество для выбранной длительности — {min_q}.")
        price_per_100 = data.get("price_per_100")
        price = (quantity / 100) * price_per_100
    elif service == "starts":
        if quantity < STARTS_MIN:
            return await message.answer(f"Минимальное количество стартов — {STARTS_MIN}.")
        price = quantity * STARTS_PRICE
    elif service in ("views", "reactions"):
        if quantity < 1:
            return await message.answer("Минимальное количество — 1.")
        if service == "views":
            price = quantity * VIEWS_PRICE
        else:
            reaction_type = data.get("reaction_type_key")
            if reaction_type is None:
                return await message.answer("Ошибка: не выбран тип реакции.")
            price_per_unit = REACTION_PRICES.get(reaction_type, 0.01)
            price = quantity * price_per_unit
    else:
        return await message.answer("Ошибка: неизвестная услуга.")

    await state.update_data(quantity=quantity, price=price)
    await message.answer(f"💰 Стоимость: {price:.2f} руб.\n\nОтправьте ссылку:")
    await state.set_state(OrderState.waiting_link)

# ====== ОБРАБОТКА ССЫЛКИ ======
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

    # Проверяем баланс
    balance = await database.get_balance(message.from_user.id)
    if balance < price:
        need = price - balance
        kb = InlineKeyboardBuilder()
        kb.button(text="💰 Пополнить баланс", callback_data="balance")
        kb.button(text="◀️ Вернуться в меню", callback_data="back_to_main")
        await message.answer(
            f"❌ Недостаточно средств на балансе.\n"
            f"Ваш баланс: {balance:.2f} руб.\n"
            f"Стоимость заказа: {price:.2f} руб.\n"
            f"Не хватает: {need:.2f} руб.\n\n"
            "Пополните баланс и повторите заказ.",
            reply_markup=kb.as_markup()
        )
        await state.clear()
        return

    # Формируем описание для комментария
    if service == "subscribers":
        comment = f"Подписчики, длительность: {data['subtype']}"
    elif service == "reactions":
        comment = f"Реакции, тип: {data['reaction_type_name']}"
        if data.get('reaction_type_key') == 'emoji_list' and 'selected_emoji' in data:
            comment += f", эмодзи: {data['selected_emoji']}"
    elif service == "starts":
        comment = f"Старты"
    else:  # views
        comment = "Просмотры"

    # Создаём заказ в статусе WAITING_CONFIRM
    try:
        await database.create_order(
            order_id=order_id,
            user_id=message.from_user.id,
            service=service,
            quantity=quantity,
            price=price,
            link=link,
            status="WAITING_CONFIRM",
            comment=comment
        )
    except Exception as e:
        logging.error(f"DB error: {e}")
        await message.answer("Ошибка при создании заказа. Попробуйте позже.")
        return await state.clear()

    # Уведомляем администраторов
    admins = await database.get_all_admins()
    for admin in admins:
        try:
            kb = InlineKeyboardBuilder()
            kb.button(text="✅ Подтвердить", callback_data=f"confirm_{order_id}")
            kb.button(text="❌ Отклонить", callback_data=f"reject_{order_id}")
            await bot.send_message(
                admin,
                f"📦 Новый заказ №{order_id} ожидает подтверждения от {message.from_user.id}\n"
                f"Услуга: {comment}\nКоличество: {quantity}\nСумма: {price:.2f} руб.\nСсылка: {link}",
                reply_markup=kb.as_markup()
            )
        except Exception as e:
            logging.error(f"Failed to notify admin {admin}: {e}")

    await message.answer(
        f"✅ Заказ №{order_id} создан и отправлен на подтверждение администратору.\n"
        f"После подтверждения средства будут списаны с баланса, и заказ начнёт выполняться.\n"
        f"Ожидайте уведомления."
    )
    await state.clear()

# ====== ПОДТВЕРЖДЕНИЕ ЗАКАЗА ======
@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_order(call: CallbackQuery):
    await call.answer()
    if not await database.is_admin(call.from_user.id):
        return
    order_id = call.data.split("_")[1]
    order = await database.get_order(order_id)
    if not order:
        return await call.message.answer("Заказ не найден.")
    if order[6] != "WAITING_CONFIRM":
        return await call.message.answer("Этот заказ уже обработан.")

    user_id = order[1]
    price = order[4]
    quantity = order[3]
    service = order[2]
    comment = order[7]
    link = order[5]

    # Списываем средства
    balance = await database.get_balance(user_id)
    if balance < price:
        await database.update_order_status(order_id, "DECLINED", "Недостаточно средств на момент подтверждения")
        await call.message.edit_text("❌ У пользователя недостаточно средств. Заказ отклонён.", reply_markup=None)
        await bot.send_message(user_id, "❌ Ваш заказ был отклонён из-за недостатка средств на балансе.")
        return

    await database.update_balance(user_id, -price)
    await database.update_order_status(order_id, "PAID", "Подтверждён администратором")

    new_balance = balance - price

    # Уведомляем пользователя
    try:
        await bot.send_message(
            user_id,
            f"✅ Заказ №{order_id} подтверждён!\n\n"
            f"{comment}\nКоличество: {quantity}\nСумма: {price:.2f} руб.\nСсылка: {link}\n\n"
            f"💰 Новый баланс: {new_balance:.2f} руб.\n\n"
            "Ваш заказ передан в работу. Ожидайте выполнения."
        )
    except TelegramForbiddenError:
        logging.warning(f"User {user_id} blocked the bot.")

    await call.message.edit_text(f"✅ Заказ №{order_id} подтверждён. Средства списаны.", reply_markup=None)

@dp.callback_query(F.data.startswith("reject_"))
async def reject_order(call: CallbackQuery):
    await call.answer()
    if not await database.is_admin(call.from_user.id):
        return
    order_id = call.data.split("_")[1]
    order = await database.get_order(order_id)
    if not order:
        return await call.message.answer("Заказ не найден.")
    if order[6] != "WAITING_CONFIRM":
        return await call.message.answer("Этот заказ уже обработан.")

    user_id = order[1]
    price = order[4]

    await database.update_order_status(order_id, "DECLINED", "Отклонён администратором")
    try:
        await bot.send_message(user_id, f"❌ Ваш заказ №{order_id} был отклонён администратором.")
    except TelegramForbiddenError:
        logging.warning(f"User {user_id} blocked the bot.")

    await call.message.edit_text(f"❌ Заказ №{order_id} отклонён.", reply_markup=None)

# ====== ФУНКЦИИ ПЛАТЕЖЕЙ (ЮKassa) ======
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

async def check_yookassa_payment(payment_id: str):
    auth = base64.b64encode(f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.yookassa.ru/v3/payments/{payment_id}", headers=headers) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return data.get('status')

# ====== ФУНКЦИИ ДЛЯ HELEKET ======
async def create_heleket_payment(amount: float, order_id: str, description: str, user_id: int):
    payload = {
        "amount": f"{amount:.2f}",
        "currency": "USDT",
        "order_id": order_id,
    }
    sorted_payload = {k: payload[k] for k in sorted(payload.keys())}
    json_data = json.dumps(sorted_payload, separators=(',', ':'))
    logging.info(f"Heleket request body: {json_data}")

    base64_data = base64.b64encode(json_data.encode()).decode()
    api_key = HELEKET_API_KEY.strip()
    merchant_id = HELEKET_MERCHANT_ID.strip()
    sign = hashlib.md5((base64_data + api_key).encode()).hexdigest()
    logging.info(f"Heleket sign: {sign}")

    headers = {
        "merchant": merchant_id,
        "sign": sign,
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{HELEKET_API_URL}/payment", headers=headers, data=json_data) as resp:
            response_text = await resp.text()
            logging.info(f"Heleket response status: {resp.status}")
            logging.info(f"Heleket response body: {response_text}")
            if resp.status != 200:
                raise Exception(f"Heleket HTTP error {resp.status}: {response_text}")
            response_json = json.loads(response_text)
            if response_json.get('state') != 0:
                raise Exception(f"Heleket error: {response_json}")
            return response_json['result']

async def check_heleket_payment(payment_uuid: str):
    payload = {"uuid": payment_uuid}
    json_data = json.dumps(payload, separators=(',', ':'))
    base64_data = base64.b64encode(json_data.encode()).decode()
    api_key = HELEKET_API_KEY.strip()
    merchant_id = HELEKET_MERCHANT_ID.strip()
    sign = hashlib.md5((base64_data + api_key).encode()).hexdigest()

    headers = {
        "merchant": merchant_id,
        "sign": sign,
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{HELEKET_API_URL}/payment/info", headers=headers, data=json_data) as resp:
            if resp.status != 200:
                logging.error(f"Heleket payment info error: HTTP {resp.status}")
                return None
            response_json = await resp.json()
            if response_json.get('state') != 0:
                logging.error(f"Heleket payment info error: {response_json}")
                return None
            return response_json['result'].get('payment_status')

# ====== КАЛЬКУЛЯТОР ======
@dp.callback_query(F.data == "calc")
async def calc_menu(call: CallbackQuery):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return

    keyboard = [
        [InlineKeyboardButton(text="Подписчики", callback_data="calc_subscribers")],
        [InlineKeyboardButton(text="Просмотры", callback_data="calc_views")],
        [InlineKeyboardButton(text="Реакции", callback_data="calc_reactions")],
        [InlineKeyboardButton(text="Старты", callback_data="calc_starts")],
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
<b>Выберите услугу из списка ниже</b>
<a href="https://t.me/">Курс на услуги</a>
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
                logging.error(f"Failed to send calc menu via direct API: {await resp.text()}")
                kb = InlineKeyboardBuilder()
                kb.button(text="Подписчики", callback_data="calc_subscribers")
                kb.button(text="Просмотры", callback_data="calc_views")
                kb.button(text="Реакции", callback_data="calc_reactions")
                kb.button(text="Старты", callback_data="calc_starts")
                kb.button(text="◀️ Вернуться назад", callback_data="back_to_main")
                kb.adjust(1)
                await call.message.answer(
                    text,
                    reply_markup=kb.as_markup(),
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )

@dp.callback_query(F.data.startswith("calc_"))
async def calc_choose(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    service = call.data.split("_")[1]
    await state.update_data(service=service)

    if service == "subscribers":
        kb = InlineKeyboardBuilder()
        for key, name in SUBSCRIBER_DURATIONS.items():
            price = SUBSCRIBER_PRICES[key]
            min_q = SUBSCRIBER_MINIMUMS[key]
            kb.button(text=f"{name} - {price}₽ за 100 чел (мин {min_q})", callback_data=f"calc_sub_dur_{key}")
        kb.button(text="◀️ Назад", callback_data="calc")
        kb.adjust(2)
        await call.message.edit_text(
            "Выберите длительность для расчёта:",
            reply_markup=kb.as_markup()
        )
        await state.set_state(CalcState.waiting_quantity)

    elif service == "reactions":
        kb = InlineKeyboardBuilder()
        for key, name in REACTION_TYPES.items():
            if key == "emoji_list":
                price_text = "1₽ за 100"
            else:
                price_text = "1₽ за 150"
            kb.button(text=f"{name} ({price_text})", callback_data=f"calc_react_{key}")
        kb.button(text="◀️ Назад", callback_data="calc")
        kb.adjust(2)
        await call.message.edit_text(
            "Выберите тип реакций для расчёта:",
            reply_markup=kb.as_markup()
        )
        await state.set_state(CalcState.waiting_reaction_type)

    elif service == "starts":
        await call.message.answer(f"Введите количество стартов (минимум {STARTS_MIN}):")
        await state.set_state(CalcState.waiting_quantity)

    else:  # views
        await call.message.answer("Введите количество просмотров:")
        await state.set_state(CalcState.waiting_quantity)

@dp.callback_query(CalcState.waiting_reaction_type, F.data.startswith("calc_react_"))
async def calc_reaction_type(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    type_key = call.data.split("_")[2]
    await state.update_data(reaction_type_key=type_key)
    await call.message.answer("Введите количество реакций:")
    await state.set_state(CalcState.waiting_quantity)

@dp.callback_query(CalcState.waiting_quantity, F.data.startswith("calc_sub_dur_"))
async def calc_subscribers_duration(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    duration_key = call.data.split("_")[3]
    price_per_100 = SUBSCRIBER_PRICES[duration_key]
    min_q = SUBSCRIBER_MINIMUMS[duration_key]
    duration_name = SUBSCRIBER_DURATIONS[duration_key]
    await state.update_data(duration=duration_name, price_per_100=price_per_100, min_quantity=min_q, service="subscribers")
    await call.message.edit_text(
        f"Длительность: {duration_name}, цена {price_per_100}₽ за 100 чел.\n"
        f"Минимальное количество: {min_q}\n\n"
        "Введите количество подписчиков:"
    )

@dp.message(CalcState.waiting_quantity)
async def calc_result(message: Message, state: FSMContext):
    if await check_ban_and_terms(message.from_user.id):
        return await state.clear()
    if not message.text or not message.text.isdigit():
        return await message.answer("Введите число!")
    quantity = int(message.text)
    data = await state.get_data()
    service = data.get("service")

    if service == "subscribers":
        min_q = data.get("min_quantity", 100)
        if quantity < min_q:
            return await message.answer(f"Минимальное количество для выбранной длительности — {min_q}.")
        price_per_100 = data.get("price_per_100")
        if price_per_100 is None:
            return await message.answer("Ошибка: не выбрана длительность.")
        price = (quantity / 100) * price_per_100
        duration = data.get("duration", "")
        await message.answer(f"💰 Стоимость {quantity} подписчиков на {duration}: {price:.2f} руб.")
    elif service == "starts":
        if quantity < STARTS_MIN:
            return await message.answer(f"Минимальное количество стартов — {STARTS_MIN}.")
        price = quantity * STARTS_PRICE
        await message.answer(f"💰 Стоимость {quantity} стартов: {price:.2f} руб.")
    elif service == "views":
        if quantity < 1:
            return await message.answer("Минимальное количество — 1.")
        price = quantity * VIEWS_PRICE
        await message.answer(f"💰 Стоимость {quantity} просмотров: {price:.2f} руб.")
    elif service == "reactions":
        if quantity < 1:
            return await message.answer("Минимальное количество — 1.")
        reaction_type = data.get("reaction_type_key")
        if reaction_type is None:
            return await message.answer("Ошибка: не выбран тип реакций.")
        price_per_unit = REACTION_PRICES.get(reaction_type, 0.01)
        price = quantity * price_per_unit
        type_name = REACTION_TYPES.get(reaction_type, "реакций")
        await message.answer(f"💰 Стоимость {quantity} {type_name}: {price:.2f} руб.")
    else:
        await message.answer("Ошибка: неизвестная услуга.")
    await state.clear()

# ====== ТЕХ. ПОДДЕРЖКА ======
@dp.callback_query(F.data == "support")
async def support(call: CallbackQuery):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return

    keyboard = [[InlineKeyboardButton(text="◀️ Вернуться назад", callback_data="back_to_main")]]

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
<b>Имеются вопросы, хотите предложить идею или у вас возникла проблема</b><tg-emoji emoji-id="5386713103213814186">❕</tg-emoji><b>

</b><blockquote><b>Напишите нам в Telegram: @nBoost_supports </b><tg-emoji emoji-id="5386748326240611247">✅</tg-emoji></blockquote>

<b>Ответ поступает в течение 24 часов</b><tg-emoji emoji-id="5386713103213814186">❕</tg-emoji>
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
                logging.error(f"Failed to send support message via direct API: {await resp.text()}")
                kb = InlineKeyboardBuilder()
                kb.button(text="◀️ Вернуться назад", callback_data="back_to_main")
                await call.message.answer(
                    text.replace("<tg-emoji", "<!-- tg-emoji").replace("</tg-emoji>", "-->"),
                    reply_markup=kb.as_markup(),
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )

# ====== FAQ ======
@dp.callback_query(F.data == "faq")
async def faq(call: CallbackQuery):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return

    keyboard = [[InlineKeyboardButton(text="◀️ Вернуться назад", callback_data="back_to_main")]]

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
<b>Все частые вопросы которые задают пользователи</b><tg-emoji emoji-id="5379748062124056162">❗️</tg-emoji><b>

</b><blockquote expandable><b>1. Почему мою заявку на накрутку отклонили?
- Вашу заявку могли отклонить по некоторым причинам, все причины по которым вам могли отклонить заявку прописаны в </b><a href="https://t.me/ineedforyou/"><b>пользовательском соглашении </b></a><b>

2. Я оплатил накрутку, но она так и не началась.
- После оплаты наша администрация проверяет вашу оплату, если оплата была произведена то мы принимаем вашу заявку на накрутку

3. Почему так долго накручиваете?
- Причин может быть несколько, но основные причины что сервера нагружены, накрутка происходит обычно в течении часа после принятия заявки.

4. Какие гарантии?
- Наш сервис предоставляет гарантию 2 дня, в случае если в период этого времени что то произошло и мы это подтвердим, то денежные средства будут вам возращены.

5. Я заказал определённое количество накрутки, но пришло не все.
- Да, такое бывает когда вы заказываете к примеру 5000 подписчиков, а приходит 4900, все из за того что некоторые боты не получают команду в обработку, обычных в течении часа доходят все боты.</b></blockquote><b>

Основные вопросы мы обговорили, в случае если у вас другой вопрос, то обращайтесь в службу поддержки бота: @nBoost_supports</b>
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
                logging.error(f"Failed to send FAQ via direct API: {await resp.text()}")
                kb = InlineKeyboardBuilder()
                kb.button(text="◀️ Вернуться назад", callback_data="back_to_main")
                await call.message.answer(
                    text.replace("<tg-emoji", "<!-- tg-emoji").replace("</tg-emoji>", "-->"),
                    reply_markup=kb.as_markup(),
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )

# ====== КНОПКА НАЗАД ======
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(call: CallbackQuery):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    try:
        await call.message.delete()
    except Exception:
        pass
    await show_main_menu(call.from_user.id)

# ====== АДМИН КОМАНДЫ ======
async def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

async def is_admin_from_db_or_config(user_id: int) -> bool:
    if user_id in STATIC_ADMINS:
        return True
    return await database.is_admin(user_id)

@dp.message(Command("ban"))
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
        await database.ban_user(user_id, message.from_user.id, reason)
        await message.answer(f"Пользователь {user_id} забанен.\nПричина: {reason}")
        try:
            await bot.send_message(user_id, f"❌ Вы заблокированы.\nПричина: {reason}")
        except:
            pass
    else:
        await state.update_data(ban_user_id=user_id)
        await message.answer("Введите причину бана:")
        await state.set_state(BanReason.waiting_reason)

@dp.message(BanReason.waiting_reason)
async def ban_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("ban_user_id")
    reason = message.text.strip()
    await database.ban_user(user_id, message.from_user.id, reason)
    await message.answer(f"Пользователь {user_id} забанен.\nПричина: {reason}")
    try:
        await bot.send_message(user_id, f"❌ Вы заблокированы.\nПричина: {reason}")
    except:
        pass
    await state.clear()

@dp.message(Command("unban"))
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
    await database.unban_user(user_id)
    await message.answer(f"Пользователь {user_id} разбанен.")
    try:
        await bot.send_message(user_id, "✅ Вы разблокированы. Теперь вы можете пользоваться ботом.")
    except:
        pass

@dp.message(Command("checkban"))
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
    ban_info = await database.get_ban_info(user_id)
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

@dp.message(Command("checkpay"))
async def check_pay(message: Message):
    if not await is_admin_from_db_or_config(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Использование: /checkpay <user_id>")
    try:
        user_id = int(args[1])
    except ValueError:
        return await message.answer("ID должен быть числом.")
    txs = await database.get_transactions(user_id, 20)
    if not txs:
        await message.answer(f"У пользователя {user_id} нет транзакций.")
        return
    text = f"📜 История транзакций пользователя {user_id} (последние 20):\n"
    for tx in txs:
        status_emoji = "✅" if tx[4] == "success" else "❌"
        text += f"{status_emoji} {tx[6][:10]} {tx[2]:+.2f} руб. ({tx[3]})\n"
    await message.answer(text)

@dp.message(Command("help"))
async def help_command(message: Message):
    await message.answer(
        "ℹ️ <b>Помощь по боту</b>\n\n"
        "Для связи с технической поддержкой используйте кнопку «Тех. Поддержка» в главном меню или напишите @nBoost_supports.\n\n"
        "Основные команды:\n"
        "/start — запуск бота и главное меню\n"
        "/help — эта справка\n"
        "Все остальные действия доступны через кнопки в интерфейсе.",
        parse_mode="HTML"
    )

@dp.message(Command("helpadmin"))
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

<b>Управление балансом:</b>
/addbalance <id> <сумма> — добавить средства на баланс
/setbalance <id> <сумма> — установить баланс

<b>Управление ботом:</b>
/stopbot [причина] — временно отключить бот для всех
/startbot — включить бот
/all — массовая рассылка

<b>Управление админами:</b>
/addadmin <id> — добавить администратора (только владелец)
/deladmin <id> — удалить администратора (только владелец)

<b>Просмотр:</b>
/checkpay <id> — история транзакций пользователя
/fixdb — диагностика структуры БД
"""
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("search"))
async def search_order(message: Message):
    if not await is_admin_from_db_or_config(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Использование: /search <order_id>")
    order_id = args[1]
    order = await database.get_order(order_id)
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

    service_info = order[2]
    if order[2] == "subscribers":
        service_info = "Подписчики"
        if order[7]:
            service_info += f" ({order[7]})"
    elif order[2] == "reactions":
        service_info = "Реакции"
        if order[7]:
            service_info += f" ({order[7]})"
    elif order[2] == "starts":
        service_info = "Старты"
    elif order[2] == "views":
        service_info = "Просмотры"

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

@dp.message(Command("addadmin"))
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
    await database.add_admin(user_id)
    await message.answer(f"Пользователь {user_id} добавлен в администраторы.")

@dp.message(Command("deladmin"))
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
    await database.remove_admin(user_id)
    await message.answer(f"Пользователь {user_id} удалён из администраторов.")

@dp.message(Command("addbalance"))
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
    await database.update_balance(user_id, amount)
    await message.answer(f"Баланс пользователя {user_id} изменён на +{amount:.2f} руб.")

@dp.message(Command("setbalance"))
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
    await database.set_balance(user_id, amount)
    await message.answer(f"Баланс пользователя {user_id} установлен на {amount:.2f} руб.")

@dp.message(Command("all"))
async def broadcast_command(message: Message, state: FSMContext):
    if not await is_owner(message.from_user.id):
        return
    await message.answer("Отправьте сообщение для рассылки всем пользователям (можно с медиа).")
    await state.set_state(BroadcastState.waiting_message)

@dp.message(BroadcastState.waiting_message)
async def broadcast_message(message: Message, state: FSMContext):
    if not await is_owner(message.from_user.id):
        return await state.clear()
    users = await database.get_all_users()
    await message.answer(f"Начинаю рассылку {len(users)} пользователям...")
    sent = 0
    blocked = 0
    for user_id in users:
        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            sent += 1
            await asyncio.sleep(0.05)
        except TelegramForbiddenError:
            blocked += 1
        except Exception as e:
            logging.error(f"Failed to send to {user_id}: {e}")
    await message.answer(f"Рассылка завершена.\nОтправлено: {sent}\nЗаблокировали бота: {blocked}")
    await state.clear()

@dp.message(Command("stopbot"))
async def stop_bot(message: Message):
    if not await is_owner(message.from_user.id):
        return
    args = message.text.split()
    reason = " ".join(args[1:]) if len(args) > 1 else "Бот временно недоступен по техническим причинам."
    await database.set_bot_active(False, reason)
    await message.answer(f"🚫 Бот остановлен. Причина: {reason}\nДоступ имеют только администраторы и владелец.")

@dp.message(Command("startbot"))
async def start_bot(message: Message):
    if not await is_owner(message.from_user.id):
        return
    await database.set_bot_active(True)
    await message.answer("✅ Бот возобновил работу. Все пользователи могут пользоваться ботом.")

@dp.message(Command("stop"))
async def stop_order(message: Message, state: FSMContext):
    if not await is_admin_from_db_or_config(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Использование: /stop <order_id> [причина]")
    order_id = args[1]
    order = await database.get_order(order_id)
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

@dp.message(StopOrderReason.waiting_reason)
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
    # Возвращаем средства, если они были списаны
    if order[6] in ("PAID", "ACCEPTED"):
        await database.update_balance(user_id, price)
    # Обновляем статус заказа
    await database.update_order_status(order_id, "DECLINED", f"Остановлен администратором: {reason}")
    # Уведомляем пользователя
    try:
        await bot.send_message(
            user_id,
            f"❌ Ваш заказ №{order_id} был остановлен администратором.\nПричина: {reason}\n"
            + ("Средства возвращены на баланс." if order[6] in ("PAID", "ACCEPTED") else "Средства не списывались.")
        )
    except TelegramForbiddenError:
        logging.warning(f"User {user_id} blocked the bot.")
    await message.answer(f"✅ Заказ №{order_id} остановлен. Средства возвращены пользователю.")

@dp.message(Command("fixdb"))
async def fixdb_command(message: Message):
    if not await database.is_admin(message.from_user.id):
        return
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

# ====== ОБРАБОТЧИКИ ПРИНЯТИЯ/ОТКЛОНЕНИЯ (устаревшие, можно оставить для совместимости) ======
@dp.callback_query(F.data.startswith("accept_"))
async def accept_order_legacy(call: CallbackQuery):
    # Этот обработчик оставлен для обратной совместимости с более старыми заказами
    await call.answer()
    if not await database.is_admin(call.from_user.id):
        return
    order_id = call.data.split("_")[1]
    order = await database.get_order(order_id)
    if not order:
        return await call.message.answer("Заказ не найден.")
    if order[6] not in ("PAID", "ACCEPTED"):
        return await call.message.answer("Этот заказ не может быть принят.")
    await database.update_order_status(order_id, "ACCEPTED", "Принят администратором")
    await call.message.edit_text(call.message.text + "\n\n✅ Заказ принят.", reply_markup=None)
    try:
        await bot.send_message(order[1], f"✅ Ваш заказ №{order_id} принят и будет выполнен.")
    except TelegramForbiddenError:
        logging.warning(f"User {order[1]} blocked the bot.")
    await call.message.answer("Заказ подтверждён.")

@dp.callback_query(F.data.startswith("decline_"))
async def decline_order_start_legacy(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if not await database.is_admin(call.from_user.id):
        return
    order_id = call.data.split("_")[1]
    order = await database.get_order(order_id)
    if not order:
        return await call.message.answer("Заказ не найден.")
    if order[6] not in ("PAID", "ACCEPTED"):
        return await call.message.answer("Этот заказ не может быть отклонён.")
    await state.update_data(order_id=order_id, order=order)
    await call.message.answer("Введите причину отклонения заказа:")
    await state.set_state(DeclineReason.waiting_reason)

@dp.message(DeclineReason.waiting_reason)
async def decline_order_reason_legacy(message: Message, state: FSMContext):
    if not await database.is_admin(message.from_user.id):
        return await state.clear()
    reason = message.text.strip()
    data = await state.get_data()
    order_id = data['order_id']
    order = data['order']
    await database.update_order_status(order_id, "DECLINED", f"Отклонён: {reason}")
    # Возвращаем средства пользователю
    await database.update_balance(order[1], order[4])
    try:
        await bot.send_message(order[1], f"❌ Ваш заказ №{order_id} отклонён.\nПричина: {reason}\nСредства возвращены на баланс.")
    except TelegramForbiddenError:
        logging.warning(f"User {order[1]} blocked the bot.")
    await message.answer(f"❌ Заказ №{order_id} отклонён. Средства возвращены.")
    await state.clear()

# ====== RUN ======
async def main():
    await database.init_db()
    for admin_id in STATIC_ADMINS:
        await database.add_admin(admin_id)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())