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
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardButton
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

# Импорт aiosqlite для диагностики
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
    waiting_emoji_page = State()

class PaymentMethodChoice(StatesGroup):
    choosing_method = State()

class CalcState(StatesGroup):
    waiting_quantity = State()
    waiting_reaction_type = State()

class DeclineReason(StatesGroup):
    waiting_reason = State()

class BroadcastState(StatesGroup):
    waiting_message = State()

class PaymentState(StatesGroup):
    waiting_for_payment = State()

# ====== Цены и параметры ======
VIEWS_PRICE = 1.0

REACTION_PRICES = {
    "custom": 0.01,
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
    "custom": "Кастомные",
    "positive": "Позитивные",
    "negative": "Негативные",
    "emoji_list": "Эмодзи из списка"
}

EMOJI_PAGE_1 = ["👍", "🤡", "💩", "❤️", "🤝", "🖕", "👀", "🍌"]
EMOJI_PAGE_2 = ["👻", "🕊", "🌲", "🗿", "🍾", "👌", "🤬"]
EMOJI_PAGES = [EMOJI_PAGE_1, EMOJI_PAGE_2]

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
<b>Приветствую!</b> <tg-emoji emoji-id="5877700484453634587">✈️</tg-emoji>
<b>Добро пожаловать в бота для накрутки статистики пользователей, просмотров и реакций

</b><blockquote><tg-emoji emoji-id="5870994129244131212">👤</tg-emoji> <b>Тех.поддержка: </b>@nBoost_supports<b>
</b><tg-emoji emoji-id="5870995486453796729">📊</tg-emoji> <b>Наш канал: </b>@channel_username</blockquote>
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
        if key in ("custom", "emoji_list"):
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

# ====== ОБРАБОТЧИКИ ДЛЯ ПОДПИСЧИКОВ ======
@dp.callback_query(SubscribersDuration.waiting_duration, F.data.startswith("sub_dur_"))
async def process_subscribers_duration(call: CallbackQuery, state: FSMContext):
    await call.answer()
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
    type_key = call.data.split("_")[2]
    logging.info(f"process_reaction_type received type_key: {type_key}")

    if type_key == "emoji":
        type_key = "emoji_list"
        logging.info("Converted old key 'emoji' to 'emoji_list'")

    if type_key not in REACTION_TYPES:
        logging.error(f"Unknown reaction type key: {type_key}")
        await call.message.answer("❌ Неизвестный тип реакции. Пожалуйста, выберите снова.")
        kb = InlineKeyboardBuilder()
        for key, name in REACTION_TYPES.items():
            price_per_unit = REACTION_PRICES[key]
            if key in ("custom", "emoji_list"):
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
        await show_emoji_page(call.message, state, page=0)
        await state.set_state(ReactionsType.waiting_reaction_emoji)
    else:
        await call.message.edit_text("Введите количество реакций (минимум 1):")
        await state.set_state(OrderState.waiting_quantity)

async def show_emoji_page(message: Message, state: FSMContext, page: int):
    data = await state.get_data()
    current_page = data.get('emoji_page', 0)
    if page == current_page:
        # Уже на этой странице, не редактируем
        return
    emoji_list = EMOJI_PAGES[page]

    kb = InlineKeyboardBuilder()
    for emoji in emoji_list:
        kb.button(text=emoji, callback_data=f"react_emoji_{emoji}")
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️ Назад", callback_data="emoji_prev"))
    if page < len(EMOJI_PAGES) - 1:
        nav_row.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data="emoji_next"))
    if nav_row:
        kb.row(*nav_row)
    kb.button(text="◀️ Назад к типам реакций", callback_data="reactions")
    kb.adjust(3)

    await message.edit_text(
        "Выберите эмодзи (страница {}):".format(page + 1),
        reply_markup=kb.as_markup()
    )
    await state.update_data(emoji_page=page)

@dp.callback_query(ReactionsType.waiting_reaction_emoji, F.data == "emoji_next")
async def emoji_next_page(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    current_page = data.get('emoji_page', 0)
    new_page = current_page + 1
    if new_page < len(EMOJI_PAGES):
        await show_emoji_page(call.message, state, new_page)
    else:
        await call.answer("Это последняя страница", show_alert=False)

@dp.callback_query(ReactionsType.waiting_reaction_emoji, F.data == "emoji_prev")
async def emoji_prev_page(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    current_page = data.get('emoji_page', 0)
    new_page = current_page - 1
    if new_page >= 0:
        await show_emoji_page(call.message, state, new_page)
    else:
        await call.answer("Это первая страница", show_alert=False)

@dp.callback_query(ReactionsType.waiting_reaction_emoji, F.data.startswith("react_emoji_"))
async def process_reaction_emoji(call: CallbackQuery, state: FSMContext):
    await call.answer()
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

    # Формируем описание для комментария
    if service == "subscribers":
        comment = f"Подписчики, длительность: {data['subtype']}"
    elif service == "reactions":
        comment = f"Реакции, тип: {data['reaction_type_name']}"
        if data.get('reaction_type_key') == 'emoji_list' and 'selected_emoji' in data:
            comment += f", эмодзи: {data['selected_emoji']}"
    else:  # views
        comment = "Просмотры"

    try:
        await database.create_order(
            order_id=order_id,
            user_id=message.from_user.id,
            service=service,
            quantity=quantity,
            price=price,
            link=link,
            status="PENDING",
            comment=comment
        )
    except Exception as e:
        logging.error(f"DB error: {e}")
        await message.answer("Ошибка при создании заказа. Попробуйте позже.")
        return await state.clear()

    await state.update_data(order_id=order_id, description=comment)

    # Выбор способа оплаты
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Банковская карта (ЮKassa)", callback_data="pay_yookassa")
    kb.button(text="₿ Криптовалюта (Heleket)", callback_data="pay_heleket")
    kb.button(text="◀️ Вернуться в главное меню", callback_data="back_to_main")
    kb.adjust(1)

    await message.answer(
        f"✅ Заказ предварительно сохранён.\n{comment}\nКоличество: {quantity}\nСумма: {price:.2f} руб.\n\nТеперь выберите способ оплаты:",
        reply_markup=kb.as_markup()
    )
    await state.set_state(PaymentMethodChoice.choosing_method)

# ====== ЮKassa ======
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

@dp.callback_query(F.data == "pay_yookassa")
async def pay_with_yookassa(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    order_id = data.get('order_id')
    if not order_id:
        await call.message.answer("Ошибка: заказ не найден. Начните заново.")
        await state.clear()
        return

    order = await database.get_order(order_id)
    if not order:
        await call.message.answer("Ошибка: заказ не найден в базе.")
        await state.clear()
        return

    price = order[4]
    description = data.get('description', f"Заказ {order_id}")
    user_id = call.from_user.id

    try:
        payment_data = await create_yookassa_payment(
            amount=price,
            description=description,
            order_id=order_id,
            user_id=user_id
        )

        payment_id = payment_data.get('id')
        confirmation_url = payment_data.get('confirmation', {}).get('confirmation_url')

        if not payment_id or not confirmation_url:
            raise Exception("Missing payment_id or confirmation_url in YooKassa response")

        await database.update_order_payment_id(order_id, payment_id)
        await database.update_order_payment_method(order_id, "yookassa")

        logging.info(f"Order {order_id} updated with payment_id={payment_id}, method=yookassa")

        # Кнопки: оплатить и проверить
        kb = InlineKeyboardBuilder()
        kb.button(text="💳 Оплатить картой", url=confirmation_url)
        kb.button(text="✅ Проверить оплату", callback_data=f"check_payment_{order_id}")
        kb.adjust(1)

        await call.message.edit_text(
            f"✅ Заказ №{order_id} готов к оплате через ЮKassa!\n\n"
            f"{description}\nСумма: {price:.2f} руб.\n\n"
            f"Для оплаты перейдите по ссылке ниже. После оплаты нажмите «Проверить оплату».",
            reply_markup=kb.as_markup(),
            disable_web_page_preview=True
        )
        await state.set_state(PaymentState.waiting_for_payment)

    except Exception as e:
        logging.error(f"YooKassa error: {e}")
        await call.message.answer("Не удалось создать платёж. Попробуйте позже.")
        await state.clear()

# ====== Heleket ======
async def create_heleket_payment(amount: float, order_id: str, description: str, user_id: int):
    payload = {
        "amount": f"{amount:.2f}",
        "currency": RUB",
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

@dp.callback_query(F.data == "pay_heleket")
async def pay_with_heleket(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    order_id = data.get('order_id')
    if not order_id:
        await call.message.answer("Ошибка: заказ не найден. Начните заново.")
        await state.clear()
        return

    order = await database.get_order(order_id)
    if not order:
        await call.message.answer("Ошибка: заказ не найден в базе.")
        await state.clear()
        return

    price = order[4]
    description = data.get('description', f"Заказ {order_id}")
    user_id = call.from_user.id

    try:
        payment_result = await create_heleket_payment(
            amount=price,
            order_id=order_id,
            description=description,
            user_id=user_id
        )

        payment_uuid = payment_result.get('uuid')
        payment_url = payment_result.get('url')

        if not payment_uuid or not payment_url:
            raise Exception("Missing uuid or url in Heleket response")

        await database.update_order_payment_id(order_id, payment_uuid)
        await database.update_order_payment_method(order_id, "heleket")

        logging.info(f"Order {order_id} updated with payment_uuid={payment_uuid}, method=heleket")

        kb = InlineKeyboardBuilder()
        kb.button(text="₿ Оплатить криптовалютой", url=payment_url)
        kb.button(text="✅ Проверить оплату", callback_data=f"check_payment_{order_id}")
        kb.adjust(1)

        await call.message.edit_text(
            f"✅ Заказ №{order_id} готов к оплате через Heleket!\n\n"
            f"{description}\nСумма: {price:.2f} руб. (эквивалент {price:.2f} USDT)\n\n"
            f"Для оплаты перейдите по ссылке ниже. После оплаты нажмите «Проверить оплату».",
            reply_markup=kb.as_markup(),
            disable_web_page_preview=True
        )
        await state.set_state(PaymentState.waiting_for_payment)

    except Exception as e:
        logging.error(f"Heleket error: {e}")
        await call.message.answer("Не удалось создать платёж через Heleket. Попробуйте позже.")
        await state.clear()

# ====== ПРОВЕРКА ОПЛАТЫ (общий обработчик) ======
async def check_yookassa_payment(payment_id: str):
    auth = base64.b64encode(f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.yookassa.ru/v3/payments/{payment_id}", headers=headers) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return data.get('status')

@dp.callback_query(F.data.startswith("check_payment_"))
async def check_payment_callback(call: CallbackQuery, state: FSMContext):
    await call.answer()
    order_id = call.data.split("_")[2]
    order = await database.get_order(order_id)
    if not order:
        await call.message.answer("Заказ не найден.")
        return

    # Проверяем статус заказа
    if order[6] in ("PAID", "ACCEPTED", "DECLINED"):
        await call.message.answer("Этот заказ уже обработан.")
        return

    payment_method = order[10]
    payment_id = order[8]
    if not payment_id:
        await call.message.answer("Нет информации о платеже.")
        return

    # Получаем статус платежа
    try:
        if payment_method == 'yookassa':
            status = await check_yookassa_payment(payment_id)
            success_status = 'succeeded'
        elif payment_method == 'heleket':
            status = await check_heleket_payment(payment_id)
            success_status = 'paid'
        else:
            await call.message.answer("Неизвестный метод оплаты.")
            return

        if status is None:
            await call.message.answer("Не удалось получить статус платежа. Попробуйте позже.")
            return

        if status == success_status:
            await database.update_order_status(order_id, "PAID", "Оплачено (подтверждено пользователем)")
            await bot.send_message(order[1], f"✅ Ваш заказ №{order_id} оплачен! Мы начали выполнение.")
            await call.message.edit_text(
                f"✅ Оплата заказа №{order_id} подтверждена!\n"
                f"Ваш заказ передан в работу.",
                reply_markup=None
            )
            # Уведомляем админов
            admins = await database.get_all_admins()
            for admin in admins:
                try:
                    await bot.send_message(admin, f"💰 Подтверждена оплата заказа №{order_id} от пользователя {order[1]}.")
                except:
                    pass
        else:
            await call.message.answer(f"❌ Платёж ещё не оплачен (статус: {status}). Попробуйте позже или обратитесь в поддержку @nBoost_supports.")
    except Exception as e:
        logging.error(f"Error checking payment: {e}")
        await call.message.answer("Произошла ошибка при проверке платежа.")

# ====== КОМАНДА /search ======
@dp.message(Command("search"))
async def search_order(message: Message):
    if not await database.is_admin(message.from_user.id) and message.from_user.id != OWNER_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Использование: /search <order_id>")
    order_id = args[1]
    order = await database.get_order(order_id)
    if not order:
        await message.answer("❌ Заказ не найден.")
        return

    # Индексы: 0-order_id,1-user_id,2-service,3-quantity,4-price,5-link,6-status,7-comment,8-payment_id,9-payment_charge_id,10-payment_method,11-created_at
    status_text = {
        "NEW": "🆕 Новый",
        "PENDING": "⏳ Ожидает оплаты",
        "PAID": "✅ Оплачен",
        "ACCEPTED": "📦 Принят в работу",
        "DECLINED": "❌ Отклонён"
    }.get(order[6], order[6])

    # Формируем описание услуги
    service_info = order[2]
    if order[2] == "subscribers":
        service_info = "Подписчики"
        if order[7]:
            service_info += f" ({order[7]})"
    elif order[2] == "reactions":
        service_info = "Реакции"
        if order[7]:
            service_info += f" ({order[7]})"
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

# ====== ДИАГНОСТИЧЕСКАЯ КОМАНДА ======
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

# ====== ОБРАБОТЧИКИ ПРИНЯТИЯ/ОТКЛОНЕНИЯ ======
@dp.callback_query(F.data.startswith("accept_"))
async def accept_order(call: CallbackQuery):
    await call.answer()
    if not await database.is_admin(call.from_user.id):
        return
    order_id = call.data.split("_")[1]
    order = await database.get_order(order_id)
    if not order:
        return await call.message.answer("Заказ не найден.")
    if order[6] not in ("PENDING", "NEW", "PAID"):
        return await call.message.answer("Этот заказ уже обработан.")
    await database.update_order_status(order_id, "ACCEPTED", "Принят администратором")
    await call.message.edit_text(call.message.text + "\n\n✅ Заказ принят.", reply_markup=None)
    try:
        await bot.send_message(order[1], f"✅ Ваш заказ №{order_id} принят и будет выполнен.")
    except TelegramForbiddenError:
        logging.warning(f"User {order[1]} blocked the bot.")
    await call.message.answer("Заказ подтверждён.")

@dp.callback_query(F.data.startswith("decline_"))
async def decline_order_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if not await database.is_admin(call.from_user.id):
        return
    order_id = call.data.split("_")[1]
    order = await database.get_order(order_id)
    if not order:
        return await call.message.answer("Заказ не найден.")
    if order[6] not in ("PENDING", "NEW", "PAID"):
        return await call.message.answer("Этот заказ уже обработан.")
    await state.update_data(order_id=order_id, order=order)
    await call.message.answer("Введите причину отклонения заказа:")
    await state.set_state(DeclineReason.waiting_reason)

@dp.message(DeclineReason.waiting_reason)
async def decline_order_reason(message: Message, state: FSMContext):
    if not await database.is_admin(message.from_user.id):
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
    await message.answer(f"❌ Заказ №{order_id} отклонён.")
    await state.clear()

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
            if key in ("custom", "emoji_list"):
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

    else:  # views
        await call.message.answer("Введите количество просмотров:")
        await state.set_state(CalcState.waiting_quantity)

@dp.callback_query(CalcState.waiting_reaction_type, F.data.startswith("calc_react_"))
async def calc_reaction_type(call: CallbackQuery, state: FSMContext):
    await call.answer()
    type_key = call.data.split("_")[2]
    await state.update_data(reaction_type_key=type_key)
    await call.message.answer("Введите количество реакций:")
    await state.set_state(CalcState.waiting_quantity)

@dp.callback_query(CalcState.waiting_quantity, F.data.startswith("calc_sub_dur_"))
async def calc_subscribers_duration(call: CallbackQuery, state: FSMContext):
    await call.answer()
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
async def ban_cmd(message: Message):
    if not await is_admin_from_db_or_config(message.from_user.id):
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

# ====== RUN ======
async def main():
    await database.init_db()
    for admin_id in STATIC_ADMINS:
        await database.add_admin(admin_id)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())