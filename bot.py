import asyncio
import logging
import random
import string
import aiohttp
import json
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.exceptions import TelegramForbiddenError
from config import BOT_TOKEN, ADMINS as STATIC_ADMINS, CARD_DETAILS, CRYPTO_DETAILS, YOOKASSA_PAYMENT_TOKEN
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
    waiting_for_invoice = State()  # после отправки счета

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
    """Возвращает True, если доступ запрещён (бан или не приняты условия)."""
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
                    **({"icon_custom_emoji_id": btn.icon_custom_emoji_id} if hasattr(btn, 'icon_custom_emoji_id') and btn.icon_custom_emoji_id else {}),
                    **({"style": btn.style} if hasattr(btn, 'style') and btn.style else {})
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
                    **({"icon_custom_emoji_id": btn.icon_custom_emoji_id} if hasattr(btn, 'icon_custom_emoji_id') and btn.icon_custom_emoji_id else {}),
                    **({"style": btn.style} if hasattr(btn, 'style') and btn.style else {})
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

# ====== ИСПРАВЛЕННЫЙ ХЕНДЛЕР С ОПЛАТОЙ ======
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
    price = data['price']  # float

    # ===== КОРРЕКТНОЕ ПРЕОБРАЗОВАНИЕ В КОПЕЙКИ =====
    price_in_kopecks = int(round(price * 100))
    if price_in_kopecks <= 0:
        return await message.answer("Сумма заказа должна быть больше 0.")

    # Формируем список товаров
    prices = [LabeledPrice(label=f"Услуга: {service}, кол-во: {quantity}", amount=price_in_kopecks)]

    # Данные для чека (email будет запрошен у пользователя через need_email=True)
    receipt_data = {
        "customer": {
            "email": ""  # будет заполнено автоматически благодаря need_email
        },
        "items": [
            {
                "description": f"{service} x{quantity}",
                "quantity": 1,
                "amount": {
                    "value": f"{price:.2f}",
                    "currency": "RUB"
                },
                "vat_code": 1  # без НДС
            }
        ]
    }

    try:
        await message.answer_invoice(
            title=f"Заказ №{order_id}",
            description=f"Услуга: {service}\nКоличество: {quantity}\nСсылка: {link}",
            payload=order_id,
            provider_token=YOOKASSA_PAYMENT_TOKEN,
            currency="RUB",
            prices=prices,
            start_parameter="create_order",
            provider_data=json.dumps({"receipt": receipt_data}),
            need_email=True,               # Telegram запросит email у пользователя
            send_email_to_provider=True,    # и передаст его в ЮKassa
            disable_web_page_preview=True
        )
    except Exception as e:
        logging.error(f"Failed to send invoice: {e}")
        await message.answer("Не удалось создать счёт. Попробуйте позже.")
        return await state.clear()

    # Сохраняем заказ в БД со статусом PENDING
    try:
        await database.create_order(
            order_id,
            message.from_user.id,
            service,
            quantity,
            price,
            link,
            status="PENDING"
        )
    except Exception as e:
        logging.error(f"DB error: {e}")
        await message.answer("Ошибка при создании заказа. Попробуйте позже.")
        return await state.clear()

    await state.set_state(PaymentState.waiting_for_invoice)

# ====== PreCheckoutQuery ======
@dp.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

# ====== Успешный платёж ======
@dp.message(F.successful_payment)
async def process_successful_payment(message: Message, state: FSMContext):
    payment_info = message.successful_payment
    order_id = payment_info.invoice_payload

    await database.update_order_status(order_id, "PAID", "Оплачено через ЮKassa")
    # Сохраняем идентификатор платежа (опционально)
    # await database.update_order_payment_charge_id(order_id, payment_info.provider_payment_charge_id)

    admins = await database.get_all_admins()
    for admin in admins:
        await bot.send_message(admin, f"💰 Поступила оплата за заказ №{order_id}")

    await message.answer(
        f"✅ Оплата по заказу №{order_id} получена!\n"
        f"Мы начали выполнение вашего заказа.",
        disable_web_page_preview=True
    )

    await state.clear()
    await show_main_menu(message.chat.id)

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
                    **({"icon_custom_emoji_id": btn.icon_custom_emoji_id} if hasattr(btn, 'icon_custom_emoji_id') and btn.icon_custom_emoji_id else {}),
                    **({"style": btn.style} if hasattr(btn, 'style') and btn.style else {})
                } for btn in row
            ] for row in keyboard
        ]
    }

    text = """
<b>Выберите услугу для подсчета стоимости</b>.
<blockquote><tg-emoji emoji-id="5870994129244131212">👤</tg-emoji><b>Нынешний курс:
Подписчики: 1 человек - 0.02₽
Реакции: 1 реакция - 0.01₽
Просмотры: 1 реакция - 0.01₽</b>
</blockquote>"""

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
                    text.replace("<tg-emoji", "<!-- tg-emoji").replace("</tg-emoji>", "-->"),
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
    await call.message.answer("Введите количество:")
    await state.set_state(CalcState.waiting_quantity)

@dp.message(CalcState.waiting_quantity)
async def calc_result(message: Message, state: FSMContext):
    if await check_ban_and_terms(message.from_user.id):
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
                    **({"icon_custom_emoji_id": btn.icon_custom_emoji_id} if hasattr(btn, 'icon_custom_emoji_id') and btn.icon_custom_emoji_id else {}),
                    **({"style": btn.style} if hasattr(btn, 'style') and btn.style else {})
                } for btn in row
            ] for row in keyboard
        ]
    }

    text = """
<b>Имеются вопросы, хотите предложить идею или у вас возникла проблема</b><tg-emoji emoji-id="5386713103213814186">❕</tg-emoji><b>

</b><blockquote><b>Напишите нам в Telegram: @support_username </b><tg-emoji emoji-id="5386748326240611247">✅</tg-emoji></blockquote>

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
                    **({"icon_custom_emoji_id": btn.icon_custom_emoji_id} if hasattr(btn, 'icon_custom_emoji_id') and btn.icon_custom_emoji_id else {}),
                    **({"style": btn.style} if hasattr(btn, 'style') and btn.style else {})
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

Основные вопросы мы обговорили, в случае если у вас другой вопрос, то обращайтесь в службу поддержки бота: @support_username</b>
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

@dp.message(Command("search"))
async def search_order(message: Message):
    if not await is_admin_from_db_or_config(message.from_user.id):
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

@dp.message(Command("addadmin"))
async def add_admin(message: Message):
    if not await is_admin_from_db_or_config(message.from_user.id):
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
    if not await is_admin_from_db_or_config(message.from_user.id):
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
    if not await is_admin_from_db_or_config(message.from_user.id):
        return
    await message.answer("Отправьте сообщение для рассылки всем пользователям (можно с медиа).")
    await state.set_state(BroadcastState.waiting_message)

@dp.message(BroadcastState.waiting_message)
async def broadcast_message(message: Message, state: FSMContext):
    if not await is_admin_from_db_or_config(message.from_user.id):
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
                message_id=message.message_id,
                disable_web_page_preview=True
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