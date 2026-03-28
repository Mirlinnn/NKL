import asyncio
import logging
import random
import string
import aiohttp
import json
import uuid
import base64
import hashlib
from datetime import datetime, timedelta
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
    waiting_promocode = State()
    waiting_confirm = State()

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

class PromocodeState(StatesGroup):
    waiting_name = State()
    waiting_discount = State()
    waiting_max_uses = State()

class ServiceState(StatesGroup):
    waiting_service_id = State()
    waiting_price = State()
    waiting_speed = State()
    waiting_text = State()

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

# ====== МЕНЮ ВЫБОРА ПЛАТФОРМЫ ======
@dp.callback_query(F.data == "order")
async def order_menu(call: CallbackQuery):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return

    keyboard = [
        [InlineKeyboardButton(text="📱 Telegram", callback_data="platform_telegram")],
        [InlineKeyboardButton(text="📘 VK", callback_data="platform_vk")],
        [InlineKeyboardButton(text="📷 Instagram", callback_data="platform_instagram")],
        [InlineKeyboardButton(text="🎵 TikTok", callback_data="platform_tiktok")],
        [InlineKeyboardButton(text="⭐ Telegram Звёзды/Премиум", callback_data="platform_stars")],
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
<b>Выберите платформу для накрутки</b>
    """

    async with aiohttp.ClientSession() as session:
        try:
            photo = FSInputFile("photo.jpg")
            form_data = aiohttp.FormData()
            form_data.add_field('chat_id', str(call.from_user.id))
            form_data.add_field('caption', text)
            form_data.add_field('parse_mode', 'HTML')
            form_data.add_field('reply_markup', json.dumps(reply_markup))
            form_data.add_field('photo', open('photo.jpg', 'rb'), filename='photo.jpg')
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            async with session.post(url, data=form_data) as resp:
                if resp.status != 200:
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                    payload = {
                        "chat_id": call.from_user.id,
                        "text": text,
                        "parse_mode": "HTML",
                        "reply_markup": reply_markup,
                        "disable_web_page_preview": True
                    }
                    await session.post(url, json=payload)
        except FileNotFoundError:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": call.from_user.id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
                "disable_web_page_preview": True
            }
            await session.post(url, json=payload)

# ====== МЕНЮ TELEGRAM ======
@dp.callback_query(F.data == "platform_telegram")
async def telegram_menu(call: CallbackQuery):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return

    keyboard = [
        [InlineKeyboardButton(text="👁 Просмотры", callback_data="tg_views")],
        [InlineKeyboardButton(text="👥 Подписчики", callback_data="tg_subscribers")],
        [InlineKeyboardButton(text="❤️ Реакции", callback_data="tg_reactions")],
        [InlineKeyboardButton(text="🔄 Дополнительно", callback_data="tg_additional")],
        [InlineKeyboardButton(text="🚀 Старты в бота", callback_data="tg_starts")],
        [InlineKeyboardButton(text="◀️ Назад к платформам", callback_data="order")]
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
<b>Выберите услугу для Telegram</b>
    """

    async with aiohttp.ClientSession() as session:
        try:
            photo = FSInputFile("photo.jpg")
            form_data = aiohttp.FormData()
            form_data.add_field('chat_id', str(call.from_user.id))
            form_data.add_field('caption', text)
            form_data.add_field('parse_mode', 'HTML')
            form_data.add_field('reply_markup', json.dumps(reply_markup))
            form_data.add_field('photo', open('photo.jpg', 'rb'), filename='photo.jpg')
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            async with session.post(url, data=form_data) as resp:
                if resp.status != 200:
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                    payload = {
                        "chat_id": call.from_user.id,
                        "text": text,
                        "parse_mode": "HTML",
                        "reply_markup": reply_markup,
                        "disable_web_page_preview": True
                    }
                    await session.post(url, json=payload)
        except FileNotFoundError:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": call.from_user.id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
                "disable_web_page_preview": True
            }
            await session.post(url, json=payload)

# ====== TELEGRAM ПРОСМОТРЫ ======
@dp.callback_query(F.data == "tg_views")
async def tg_views(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(platform="telegram", category="views", service_name="Просмотры Telegram")
    await call.message.edit_text("Введите количество просмотров (минимум 1):")
    await state.set_state(OrderState.waiting_quantity)

# ====== TELEGRAM ПОДПИСЧИКИ ======
@dp.callback_query(F.data == "tg_subscribers")
async def tg_subscribers_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(platform="telegram", category="subscribers")

    kb = InlineKeyboardBuilder()
    durations = [
        ("1 день", "day"),
        ("3 дня", "3days"),
        ("7 дней", "7days"),
        ("30 дней", "30days"),
        ("Навсегда", "forever")
    ]
    for name, key in durations:
        kb.button(text=name, callback_data=f"tg_sub_{key}")
    kb.button(text="◀️ Назад", callback_data="platform_telegram")
    kb.adjust(2)

    await call.message.edit_text(
        "Выберите длительность подписки:",
        reply_markup=kb.as_markup()
    )
    await state.set_state(OrderState.waiting_quantity)

@dp.callback_query(F.data.startswith("tg_sub_"))
async def tg_sub_duration(call: CallbackQuery, state: FSMContext):
    await call.answer()
    key = call.data.split("_")[2]
    names = {"day": "1 день", "3days": "3 дня", "7days": "7 дней", "30days": "30 дней", "forever": "Навсегда"}
    name = names.get(key, "Подписчики")
    await state.update_data(subtype=name, service_name=f"Подписчики Telegram ({name})")
    await call.message.edit_text(f"Выбраны подписчики Telegram: {name}\nВведите количество (минимум 100):")
    await state.set_state(OrderState.waiting_quantity)

# ====== TELEGRAM РЕАКЦИИ ======
@dp.callback_query(F.data == "tg_reactions")
async def tg_reactions_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(platform="telegram", category="reactions")

    kb = InlineKeyboardBuilder()
    reactions = [
        ("Позитивные реакции", "positive"),
        ("Негативные реакции", "negative"),
        ("Реакции из списка", "emoji_list"),
        ("Премиум реакции", "premium"),
        ("Звездные реакции", "stars")
    ]
    for name, key in reactions:
        kb.button(text=name, callback_data=f"tg_react_{key}")
    kb.button(text="◀️ Назад", callback_data="platform_telegram")
    kb.adjust(2)

    await call.message.edit_text(
        "Выберите тип реакций:",
        reply_markup=kb.as_markup()
    )
    await state.set_state(OrderState.waiting_quantity)

@dp.callback_query(F.data.startswith("tg_react_"))
async def tg_reaction_type(call: CallbackQuery, state: FSMContext):
    await call.answer()
    key = call.data.split("_")[2]
    names = {
        "positive": "Позитивные", "negative": "Негативные",
        "emoji_list": "Реакции из списка", "premium": "Премиум", "stars": "Звездные"
    }
    name = names.get(key, "Реакции")
    await state.update_data(subtype=name, reaction_type_key=key, service_name=f"Реакции Telegram ({name})")
    await call.message.edit_text(f"Выбраны реакции: {name}\nВведите количество (минимум 1):")
    await state.set_state(OrderState.waiting_quantity)

# ====== TELEGRAM ДОПОЛНИТЕЛЬНО ======
@dp.callback_query(F.data == "tg_additional")
async def tg_additional_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(platform="telegram", category="additional")

    kb = InlineKeyboardBuilder()
    items = [
        ("Голоса на опрос", "polls"),
        ("Комментарии (свои)", "comments_custom"),
        ("Комментарии по теме поста", "comments_topic"),
        ("Активные подписчики", "active_subs")
    ]
    for name, key in items:
        kb.button(text=name, callback_data=f"tg_add_{key}")
    kb.button(text="◀️ Назад", callback_data="platform_telegram")
    kb.adjust(2)

    await call.message.edit_text(
        "Выберите дополнительную услугу:",
        reply_markup=kb.as_markup()
    )
    await state.set_state(OrderState.waiting_quantity)

@dp.callback_query(F.data.startswith("tg_add_"))
async def tg_additional_type(call: CallbackQuery, state: FSMContext):
    await call.answer()
    key = call.data.split("_")[2]
    names = {
        "polls": "Голоса на опрос", "comments_custom": "Комментарии (свои)",
        "comments_topic": "Комментарии по теме поста", "active_subs": "Активные подписчики"
    }
    name = names.get(key, "Дополнительная услуга")
    await state.update_data(subtype=name, service_name=f"Telegram {name}")
    await call.message.edit_text(f"Выбрано: {name}\nВведите количество (минимум 1):")
    await state.set_state(OrderState.waiting_quantity)

# ====== TELEGRAM СТАРТЫ В БОТА ======
@dp.callback_query(F.data == "tg_starts")
async def tg_starts_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(platform="telegram", category="starts")

    kb = InlineKeyboardBuilder()
    start_types = [
        ("Принимают реф коды", "ref"),
        ("Просто старт бота", "simple"),
        ("Запуск из поиска", "search"),
        ("ИИ старты", "ai")
    ]
    for name, key in start_types:
        kb.button(text=name, callback_data=f"tg_start_{key}")
    kb.button(text="◀️ Назад", callback_data="platform_telegram")
    kb.adjust(2)

    await call.message.edit_text(
        "Выберите тип стартов:",
        reply_markup=kb.as_markup()
    )
    await state.set_state(OrderState.waiting_quantity)

@dp.callback_query(F.data.startswith("tg_start_"))
async def tg_start_type(call: CallbackQuery, state: FSMContext):
    await call.answer()
    key = call.data.split("_")[2]
    names = {
        "ref": "Принимают реф коды", "simple": "Просто старт бота",
        "search": "Запуск из поиска", "ai": "ИИ старты"
    }
    name = names.get(key, "Старты")
    await state.update_data(subtype=name, service_name=f"Старты в бота ({name})")
    await call.message.edit_text(f"Выбраны старты: {name}\nВведите количество (минимум 10):")
    await state.set_state(OrderState.waiting_quantity)

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

# ====== МЕНЮ VK ======
@dp.callback_query(F.data == "platform_vk")
async def vk_menu(call: CallbackQuery):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return

    keyboard = [
        [InlineKeyboardButton(text="👥 Подписчики", callback_data="vk_subscribers")],
        [InlineKeyboardButton(text="❤️ Лайки", callback_data="vk_likes")],
        [InlineKeyboardButton(text="👁 Просмотры", callback_data="vk_views")],
        [InlineKeyboardButton(text="🗳 Голоса на опрос (медленные)", callback_data="vk_polls")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="order")]
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
<b>Выберите услугу для VK</b>
    """

    async with aiohttp.ClientSession() as session:
        try:
            photo = FSInputFile("photo.jpg")
            form_data = aiohttp.FormData()
            form_data.add_field('chat_id', str(call.from_user.id))
            form_data.add_field('caption', text)
            form_data.add_field('parse_mode', 'HTML')
            form_data.add_field('reply_markup', json.dumps(reply_markup))
            form_data.add_field('photo', open('photo.jpg', 'rb'), filename='photo.jpg')
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            async with session.post(url, data=form_data) as resp:
                if resp.status != 200:
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                    payload = {
                        "chat_id": call.from_user.id,
                        "text": text,
                        "parse_mode": "HTML",
                        "reply_markup": reply_markup,
                        "disable_web_page_preview": True
                    }
                    await session.post(url, json=payload)
        except FileNotFoundError:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": call.from_user.id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
                "disable_web_page_preview": True
            }
            await session.post(url, json=payload)

# ====== VK ПОДПИСЧИКИ ======
@dp.callback_query(F.data == "vk_subscribers")
async def vk_subscribers_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(platform="vk", category="subscribers")

    kb = InlineKeyboardBuilder()
    sub_types = [
        ("Меньше собак", "less_dogs"),
        ("30 дней гарантия", "30days"),
        ("90 дней гарантия, живые люди", "90days_live")
    ]
    for name, key in sub_types:
        kb.button(text=name, callback_data=f"vk_sub_{key}")
    kb.button(text="◀️ Назад", callback_data="platform_vk")
    kb.adjust(2)

    await call.message.edit_text(
        "Выберите тип подписчиков VK:",
        reply_markup=kb.as_markup()
    )
    await state.set_state(OrderState.waiting_quantity)

@dp.callback_query(F.data.startswith("vk_sub_"))
async def vk_sub_type(call: CallbackQuery, state: FSMContext):
    await call.answer()
    key = call.data.split("_")[2]
    names = {"less_dogs": "Меньше собак", "30days": "30 дней гарантия", "90days_live": "90 дней гарантия, живые люди"}
    name = names.get(key, "Подписчики VK")
    await state.update_data(subtype=name, service_name=f"Подписчики VK ({name})")
    await call.message.edit_text(f"Выбраны подписчики VK: {name}\nВведите количество (мин 100):")
    await state.set_state(OrderState.waiting_quantity)

# ====== VK ЛАЙКИ ======
@dp.callback_query(F.data == "vk_likes")
async def vk_likes_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(platform="vk", category="likes")

    kb = InlineKeyboardBuilder()
    like_types = [
        ("Лайк на пост", "post"),
        ("Лайк на комментарий", "comment")
    ]
    for name, key in like_types:
        kb.button(text=name, callback_data=f"vk_like_{key}")
    kb.button(text="◀️ Назад", callback_data="platform_vk")
    kb.adjust(2)

    await call.message.edit_text(
        "Выберите тип лайков VK:",
        reply_markup=kb.as_markup()
    )
    await state.set_state(OrderState.waiting_quantity)

@dp.callback_query(F.data.startswith("vk_like_"))
async def vk_like_type(call: CallbackQuery, state: FSMContext):
    await call.answer()
    key = call.data.split("_")[2]
    names = {"post": "Лайк на пост", "comment": "Лайк на комментарий"}
    name = names.get(key, "Лайки VK")
    await state.update_data(subtype=name, service_name=f"Лайки VK ({name})")
    await call.message.edit_text(f"Выбраны лайки VK: {name}\nВведите количество (мин 1):")
    await state.set_state(OrderState.waiting_quantity)

# ====== VK ПРОСМОТРЫ ======
@dp.callback_query(F.data == "vk_views")
async def vk_views_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(platform="vk", category="views")

    kb = InlineKeyboardBuilder()
    view_types = [
        ("Просмотры на пост", "post"),
        ("Автопросмотры 30 дней", "auto30"),
        ("Просмотры на видео", "video"),
        ("Просмотры на клипы", "clips"),
        ("Просмотры плейлиста/альбома", "playlist")
    ]
    for name, key in view_types:
        kb.button(text=name, callback_data=f"vk_view_{key}")
    kb.button(text="◀️ Назад", callback_data="platform_vk")
    kb.adjust(2)

    await call.message.edit_text(
        "Выберите тип просмотров VK:",
        reply_markup=kb.as_markup()
    )
    await state.set_state(OrderState.waiting_quantity)

@dp.callback_query(F.data.startswith("vk_view_"))
async def vk_view_type(call: CallbackQuery, state: FSMContext):
    await call.answer()
    key = call.data.split("_")[2]
    names = {
        "post": "Просмотры на пост", "auto30": "Автопросмотры 30 дней",
        "video": "Просмотры на видео", "clips": "Просмотры на клипы",
        "playlist": "Просмотры плейлиста/альбома"
    }
    name = names.get(key, "Просмотры VK")
    await state.update_data(subtype=name, service_name=f"Просмотры VK ({name})")
    await call.message.edit_text(f"Выбраны просмотры VK: {name}\nВведите количество (мин 1):")
    await state.set_state(OrderState.waiting_quantity)

# ====== VK ГОЛОСА НА ОПРОС ======
@dp.callback_query(F.data == "vk_polls")
async def vk_polls_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(platform="vk", category="polls", service_name="Голоса на опрос (медленные)")
    await call.message.edit_text("Введите количество голосов (мин 1):")
    await state.set_state(OrderState.waiting_quantity)

# ====== МЕНЮ INSTAGRAM ======
@dp.callback_query(F.data == "platform_instagram")
async def instagram_menu(call: CallbackQuery):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return

    keyboard = [
        [InlineKeyboardButton(text="👁 Просмотры", callback_data="ig_views")],
        [InlineKeyboardButton(text="👥 Подписчики", callback_data="ig_subscribers")],
        [InlineKeyboardButton(text="❤️ Лайки", callback_data="ig_likes")],
        [InlineKeyboardButton(text="💬 Комментарии", callback_data="ig_comments")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="order")]
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
<b>Выберите услугу для Instagram</b>
    """

    async with aiohttp.ClientSession() as session:
        try:
            photo = FSInputFile("photo.jpg")
            form_data = aiohttp.FormData()
            form_data.add_field('chat_id', str(call.from_user.id))
            form_data.add_field('caption', text)
            form_data.add_field('parse_mode', 'HTML')
            form_data.add_field('reply_markup', json.dumps(reply_markup))
            form_data.add_field('photo', open('photo.jpg', 'rb'), filename='photo.jpg')
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            async with session.post(url, data=form_data) as resp:
                if resp.status != 200:
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                    payload = {
                        "chat_id": call.from_user.id,
                        "text": text,
                        "parse_mode": "HTML",
                        "reply_markup": reply_markup,
                        "disable_web_page_preview": True
                    }
                    await session.post(url, json=payload)
        except FileNotFoundError:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": call.from_user.id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
                "disable_web_page_preview": True
            }
            await session.post(url, json=payload)

# ====== INSTAGRAM ПОДПИСЧИКИ ======
@dp.callback_query(F.data == "ig_subscribers")
async def ig_subscribers_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(platform="instagram", category="subscribers")

    kb = InlineKeyboardBuilder()
    sub_types = [
        ("Новые профили", "new"),
        ("Старые профили", "old"),
        ("Старые профили 2", "old2"),
        ("30 дней гарантии", "30days"),
        ("60 дней гарантии", "60days"),
        ("Навсегда", "forever")
    ]
    for name, key in sub_types:
        kb.button(text=name, callback_data=f"ig_sub_{key}")
    kb.button(text="◀️ Назад", callback_data="platform_instagram")
    kb.adjust(2)

    await call.message.edit_text(
        "Выберите тип подписчиков Instagram:",
        reply_markup=kb.as_markup()
    )
    await state.set_state(OrderState.waiting_quantity)

@dp.callback_query(F.data.startswith("ig_sub_"))
async def ig_sub_type(call: CallbackQuery, state: FSMContext):
    await call.answer()
    key = call.data.split("_")[2]
    names = {
        "new": "Новые профили", "old": "Старые профили", "old2": "Старые профили 2",
        "30days": "30 дней гарантии", "60days": "60 дней гарантии", "forever": "Навсегда"
    }
    name = names.get(key, "Подписчики Instagram")
    await state.update_data(subtype=name, service_name=f"Подписчики Instagram ({name})")
    await call.message.edit_text(f"Выбраны подписчики Instagram: {name}\nВведите количество (мин 100):")
    await state.set_state(OrderState.waiting_quantity)

# ====== INSTAGRAM ПРОСМОТРЫ ======
@dp.callback_query(F.data == "ig_views")
async def ig_views_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(platform="instagram", category="views")

    kb = InlineKeyboardBuilder()
    view_types = [
        ("Просмотры видео", "video"),
        ("Просмотры фото (с охватами)", "photo"),
        ("Просмотры видео (с охватами)", "video_reach")
    ]
    for name, key in view_types:
        kb.button(text=name, callback_data=f"ig_view_{key}")
    kb.button(text="◀️ Назад", callback_data="platform_instagram")
    kb.adjust(2)

    await call.message.edit_text(
        "Выберите тип просмотров Instagram:",
        reply_markup=kb.as_markup()
    )
    await state.set_state(OrderState.waiting_quantity)

@dp.callback_query(F.data.startswith("ig_view_"))
async def ig_view_type(call: CallbackQuery, state: FSMContext):
    await call.answer()
    key = call.data.split("_")[2]
    names = {
        "video": "Просмотры видео", "photo": "Просмотры фото (с охватами)",
        "video_reach": "Просмотры видео (с охватами)"
    }
    name = names.get(key, "Просмотры Instagram")
    await state.update_data(subtype=name, service_name=f"Просмотры Instagram ({name})")
    await call.message.edit_text(f"Выбраны просмотры Instagram: {name}\nВведите количество (мин 1):")
    await state.set_state(OrderState.waiting_quantity)

# ====== INSTAGRAM ЛАЙКИ ======
@dp.callback_query(F.data == "ig_likes")
async def ig_likes_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(platform="instagram", category="likes")

    kb = InlineKeyboardBuilder()
    like_types = [
        ("Без гарантии (макс 500000)", "no_guarantee"),
        ("Гарантия 30 дней (макс 500000)", "30days"),
        ("Повышенное микс (макс 1.000.000)", "mix"),
        ("Навсегда (макс 1.000.000)", "forever")
    ]
    for name, key in like_types:
        kb.button(text=name, callback_data=f"ig_like_{key}")
    kb.button(text="◀️ Назад", callback_data="platform_instagram")
    kb.adjust(2)

    await call.message.edit_text(
        "Выберите тип лайков Instagram:",
        reply_markup=kb.as_markup()
    )
    await state.set_state(OrderState.waiting_quantity)

@dp.callback_query(F.data.startswith("ig_like_"))
async def ig_like_type(call: CallbackQuery, state: FSMContext):
    await call.answer()
    key = call.data.split("_")[2]
    names = {
        "no_guarantee": "Без гарантии", "30days": "Гарантия 30 дней",
        "mix": "Повышенное микс", "forever": "Навсегда"
    }
    name = names.get(key, "Лайки Instagram")
    await state.update_data(subtype=name, service_name=f"Лайки Instagram ({name})")
    await call.message.edit_text(f"Выбраны лайки Instagram: {name}\nВведите количество (мин 1):")
    await state.set_state(OrderState.waiting_quantity)

# ====== INSTAGRAM КОММЕНТАРИИ ======
@dp.callback_query(F.data == "ig_comments")
async def ig_comments_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(platform="instagram", category="comments", service_name="Комментарии Instagram (свои)")
    await call.message.edit_text("Введите количество комментариев (мин 1):")
    await state.set_state(OrderState.waiting_quantity)

# ====== МЕНЮ TIKTOK ======
@dp.callback_query(F.data == "platform_tiktok")
async def tiktok_menu(call: CallbackQuery):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return

    keyboard = [
        [InlineKeyboardButton(text="👥 Подписчики", callback_data="tt_subscribers")],
        [InlineKeyboardButton(text="👁 Просмотры", callback_data="tt_views")],
        [InlineKeyboardButton(text="🔖 Сохранение/репосты", callback_data="tt_saves")],
        [InlineKeyboardButton(text="👀 Зрители на Трансляцию", callback_data="tt_live_viewers")],
        [InlineKeyboardButton(text="🤖 Зрители на Трансляцию ИИ", callback_data="tt_live_ai")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="order")]
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
<b>Выберите услугу для TikTok</b>
    """

    async with aiohttp.ClientSession() as session:
        try:
            photo = FSInputFile("photo.jpg")
            form_data = aiohttp.FormData()
            form_data.add_field('chat_id', str(call.from_user.id))
            form_data.add_field('caption', text)
            form_data.add_field('parse_mode', 'HTML')
            form_data.add_field('reply_markup', json.dumps(reply_markup))
            form_data.add_field('photo', open('photo.jpg', 'rb'), filename='photo.jpg')
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            async with session.post(url, data=form_data) as resp:
                if resp.status != 200:
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                    payload = {
                        "chat_id": call.from_user.id,
                        "text": text,
                        "parse_mode": "HTML",
                        "reply_markup": reply_markup,
                        "disable_web_page_preview": True
                    }
                    await session.post(url, json=payload)
        except FileNotFoundError:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": call.from_user.id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
                "disable_web_page_preview": True
            }
            await session.post(url, json=payload)

# ====== TIKTOK ПОДПИСЧИКИ ======
@dp.callback_query(F.data == "tt_subscribers")
async def tt_subscribers_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(platform="tiktok", category="subscribers")

    kb = InlineKeyboardBuilder()
    sub_types = [
        ("Без гарантий", "no_guarantee"),
        ("30 дней гарантии", "30days"),
        ("Реальные люди", "real")
    ]
    for name, key in sub_types:
        kb.button(text=name, callback_data=f"tt_sub_{key}")
    kb.button(text="◀️ Назад", callback_data="platform_tiktok")
    kb.adjust(2)

    await call.message.edit_text(
        "Выберите тип подписчиков TikTok:",
        reply_markup=kb.as_markup()
    )
    await state.set_state(OrderState.waiting_quantity)

@dp.callback_query(F.data.startswith("tt_sub_"))
async def tt_sub_type(call: CallbackQuery, state: FSMContext):
    await call.answer()
    key = call.data.split("_")[2]
    names = {"no_guarantee": "Без гарантий", "30days": "30 дней гарантии", "real": "Реальные люди"}
    name = names.get(key, "Подписчики TikTok")
    await state.update_data(subtype=name, service_name=f"Подписчики TikTok ({name})")
    await call.message.edit_text(f"Выбраны подписчики TikTok: {name}\nВведите количество (мин 100):")
    await state.set_state(OrderState.waiting_quantity)

# ====== TIKTOK ПРОСМОТРЫ ======
@dp.callback_query(F.data == "tt_views")
async def tt_views_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(platform="tiktok", category="views")

    kb = InlineKeyboardBuilder()
    view_types = [
        ("Гарантия навсегда", "forever"),
        ("Без гарантий", "no_guarantee"),
        ("Для монетизации", "monetization")
    ]
    for name, key in view_types:
        kb.button(text=name, callback_data=f"tt_view_{key}")
    kb.button(text="◀️ Назад", callback_data="platform_tiktok")
    kb.adjust(2)

    await call.message.edit_text(
        "Выберите тип просмотров TikTok:",
        reply_markup=kb.as_markup()
    )
    await state.set_state(OrderState.waiting_quantity)

@dp.callback_query(F.data.startswith("tt_view_"))
async def tt_view_type(call: CallbackQuery, state: FSMContext):
    await call.answer()
    key = call.data.split("_")[2]
    names = {"forever": "Гарантия навсегда", "no_guarantee": "Без гарантий", "monetization": "Для монетизации"}
    name = names.get(key, "Просмотры TikTok")
    await state.update_data(subtype=name, service_name=f"Просмотры TikTok ({name})")
    await call.message.edit_text(f"Выбраны просмотры TikTok: {name}\nВведите количество (мин 1):")
    await state.set_state(OrderState.waiting_quantity)

# ====== TIKTOK СОХРАНЕНИЕ/РЕПОСТЫ ======
@dp.callback_query(F.data == "tt_saves")
async def tt_saves_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(platform="tiktok", category="saves")

    kb = InlineKeyboardBuilder()
    save_types = [
        ("Сохранение", "save"),
        ("Репосты (живые)", "live_rep"),
        ("Репосты (быстрые)", "fast_rep")
    ]
    for name, key in save_types:
        kb.button(text=name, callback_data=f"tt_save_{key}")
    kb.button(text="◀️ Назад", callback_data="platform_tiktok")
    kb.adjust(2)

    await call.message.edit_text(
        "Выберите тип сохранений/репостов TikTok:",
        reply_markup=kb.as_markup()
    )
    await state.set_state(OrderState.waiting_quantity)

@dp.callback_query(F.data.startswith("tt_save_"))
async def tt_save_type(call: CallbackQuery, state: FSMContext):
    await call.answer()
    key = call.data.split("_")[2]
    names = {"save": "Сохранение", "live_rep": "Репосты (живые)", "fast_rep": "Репосты (быстрые)"}
    name = names.get(key, "Сохранения/репосты TikTok")
    await state.update_data(subtype=name, service_name=f"Сохранения/репосты TikTok ({name})")
    await call.message.edit_text(f"Выбраны сохранения/репосты TikTok: {name}\nВведите количество (мин 1):")
    await state.set_state(OrderState.waiting_quantity)

# ====== TIKTOK ЗРИТЕЛИ НА ТРАНСЛЯЦИЮ ======
@dp.callback_query(F.data == "tt_live_viewers")
async def tt_live_viewers_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(platform="tiktok", category="live_viewers")

    durations = [15, 30, 60, 90, 120, 180, 240, 300, 360]
    kb = InlineKeyboardBuilder()
    for d in durations:
        kb.button(text=f"{d} минут", callback_data=f"tt_live_{d}")
    kb.button(text="◀️ Назад", callback_data="platform_tiktok")
    kb.adjust(3)

    await call.message.edit_text(
        "Выберите длительность зрителей на трансляцию:",
        reply_markup=kb.as_markup()
    )
    await state.set_state(OrderState.waiting_quantity)

@dp.callback_query(F.data.startswith("tt_live_") and not F.data.startswith("tt_live_ai"))
async def tt_live_duration(call: CallbackQuery, state: FSMContext):
    await call.answer()
    minutes = call.data.split("_")[2]
    await state.update_data(subtype=f"{minutes} минут", service_name=f"Зрители на трансляцию ({minutes} мин)")
    await call.message.edit_text(f"Выбраны зрители на трансляцию: {minutes} минут\nВведите количество зрителей (мин 1):")
    await state.set_state(OrderState.waiting_quantity)

# ====== TIKTOK ЗРИТЕЛИ НА ТРАНСЛЯЦИЮ ИИ ======
@dp.callback_query(F.data == "tt_live_ai")
async def tt_live_ai_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(platform="tiktok", category="live_ai")

    durations = [15, 30, 60, 90, 120, 150, 180, 210, 240]
    kb = InlineKeyboardBuilder()
    for d in durations:
        kb.button(text=f"{d} минут", callback_data=f"tt_live_ai_{d}")
    kb.button(text="◀️ Назад", callback_data="platform_tiktok")
    kb.adjust(3)

    await call.message.edit_text(
        "Выберите длительность зрителей на трансляцию ИИ:",
        reply_markup=kb.as_markup()
    )
    await state.set_state(OrderState.waiting_quantity)

@dp.callback_query(F.data.startswith("tt_live_ai_"))
async def tt_live_ai_duration(call: CallbackQuery, state: FSMContext):
    await call.answer()
    minutes = call.data.split("_")[3]
    await state.update_data(subtype=f"{minutes} минут", service_name=f"Зрители на трансляцию ИИ ({minutes} мин)")
    await call.message.edit_text(f"Выбраны зрители на трансляцию ИИ: {minutes} минут\nВведите количество зрителей (мин 1):")
    await state.set_state(OrderState.waiting_quantity)

# ====== МЕНЮ TELEGRAM ЗВЁЗДЫ/ПРЕМИУМ ======
@dp.callback_query(F.data == "platform_stars")
async def stars_menu(call: CallbackQuery):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return

    keyboard = [
        [InlineKeyboardButton(text="⭐ Телеграм звёзды", callback_data="stars_stars")],
        [InlineKeyboardButton(text="👑 Телеграм премиум", callback_data="stars_premium")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="order")]
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
<b>Выберите услугу для Telegram Звёзды/Премиум</b>
    """

    async with aiohttp.ClientSession() as session:
        try:
            photo = FSInputFile("photo.jpg")
            form_data = aiohttp.FormData()
            form_data.add_field('chat_id', str(call.from_user.id))
            form_data.add_field('caption', text)
            form_data.add_field('parse_mode', 'HTML')
            form_data.add_field('reply_markup', json.dumps(reply_markup))
            form_data.add_field('photo', open('photo.jpg', 'rb'), filename='photo.jpg')
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            async with session.post(url, data=form_data) as resp:
                if resp.status != 200:
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                    payload = {
                        "chat_id": call.from_user.id,
                        "text": text,
                        "parse_mode": "HTML",
                        "reply_markup": reply_markup,
                        "disable_web_page_preview": True
                    }
                    await session.post(url, json=payload)
        except FileNotFoundError:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": call.from_user.id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
                "disable_web_page_preview": True
            }
            await session.post(url, json=payload)

@dp.callback_query(F.data == "stars_stars")
async def stars_stars_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(platform="stars", category="stars", service_name="Телеграм звёзды")
    await call.message.edit_text("Введите количество звёзд (мин 1):")
    await state.set_state(OrderState.waiting_quantity)

@dp.callback_query(F.data == "stars_premium")
async def stars_premium_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    await state.update_data(platform="stars", category="premium")

    kb = InlineKeyboardBuilder()
    durations = [
        ("3 месяца", "3months"),
        ("6 месяцев", "6months"),
        ("12 месяцев", "12months")
    ]
    for name, key in durations:
        kb.button(text=name, callback_data=f"prem_{key}")
    kb.button(text="◀️ Назад", callback_data="platform_stars")
    kb.adjust(2)

    await call.message.edit_text(
        "Выберите длительность премиума:",
        reply_markup=kb.as_markup()
    )
    await state.set_state(OrderState.waiting_quantity)

@dp.callback_query(F.data.startswith("prem_"))
async def premium_duration(call: CallbackQuery, state: FSMContext):
    await call.answer()
    key = call.data.split("_")[1]
    names = {"3months": "3 месяца", "6months": "6 месяцев", "12months": "12 месяцев"}
    name = names.get(key, "Премиум")
    await state.update_data(subtype=name, service_name=f"Телеграм премиум ({name})")
    await call.message.edit_text(f"Выбран премиум: {name}\nВведите количество (мин 1):")
    await state.set_state(OrderState.waiting_quantity)

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

# ====== БАЛАНС И ПОПОЛНЕНИЕ ======
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
        f"Введите сумму пополнения (от 1.00 руб.):",
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
        f"Введите сумму пополнения (от 5.00 руб.):",
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
    if method == "yookassa" and amount < 1.0:
        return await message.answer("Минимальная сумма пополнения: 1.00 руб.")
    if method == "heleket" and amount < 5.0:
        return await message.answer("Минимальная сумма пополнения: 5.00 руб.")

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
            f"Создан счёт на пополнение баланса на {amount:.2f} руб.\n"
            "После оплаты нажмите «Проверить оплату».",
            reply_markup=kb.as_markup(),
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
            f"Создан счёт на пополнение баланса на {amount:.2f} руб. (эквивалент в USDT).\n"
            "После оплаты нажмите «Проверить оплату».",
            reply_markup=kb.as_markup(),
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
        await call.message.edit_text(f"✅ Баланс пополнен на {tx[2]:.2f} руб.", reply_markup=None)
        await call.message.answer("Теперь вы можете заказывать услуги.")
    else:
        await call.message.answer(f"❌ Платёж не оплачен (статус: {status}). Попробуйте позже.")

# ====== ОБРАБОТКА КОЛИЧЕСТВА ======
@dp.message(OrderState.waiting_quantity)
async def get_quantity(message: Message, state: FSMContext):
    if await check_ban_and_terms(message.from_user.id):
        return await state.clear()
    if not message.text or not message.text.isdigit():
        return await message.answer("Введите число!")
    quantity = int(message.text)
    data = await state.get_data()
    platform = data.get("platform")
    category = data.get("category")
    service_name = data.get("service_name", "услуга")
    
    # Определяем минимальное количество в зависимости от услуги
    min_q = 1
    if platform == "telegram" and category == "subscribers":
        min_q = 100
    elif platform == "telegram" and category == "starts":
        min_q = 10
    elif platform == "vk" and category == "subscribers":
        min_q = 100
    elif platform == "instagram" and category == "subscribers":
        min_q = 100
    elif platform == "tiktok" and category == "subscribers":
        min_q = 100
    elif platform == "instagram" and category == "likes":
        # Проверяем максимальное количество для лайков Instagram
        subtype = data.get("subtype", "")
        if subtype == "Без гарантии" or subtype == "Гарантия 30 дней":
            if quantity > 500000:
                return await message.answer("Максимальное количество для выбранного типа лайков: 500000")
        elif subtype == "Повышенное микс" or subtype == "Навсегда":
            if quantity > 1000000:
                return await message.answer("Максимальное количество для выбранного типа лайков: 1000000")
    else:
        min_q = 1
    
    if quantity < min_q:
        return await message.answer(f"Минимальное количество для выбранной услуги: {min_q}.")
    
    # Цена пока временно 1 рубль за единицу (позже будет браться из БД)
    price = quantity * 1.0
    await state.update_data(quantity=quantity, price=price, service_name=service_name)
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
    await state.update_data(link=link, order_id=order_id)
    
    # Проверяем баланс
    balance = await database.get_balance(message.from_user.id)
    price = data['price']
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
    
    # Показываем подтверждение
    service_desc = data.get('service_name', 'Услуга')
    if data.get('subtype'):
        service_desc += f" ({data['subtype']})"
    
    text = f"""
<b>Подтвердите заказ</b>

🆔 Номер заказа: {order_id}
📦 Услуга: {service_desc}
🔢 Количество: {data['quantity']}
💰 Цена: {price:.2f} руб.
🔗 Ссылка: {link}

Введите промокод (если есть) или нажмите «Подтвердить» для оплаты.
"""
    kb = InlineKeyboardBuilder()
    kb.button(text="🎁 Ввести промокод", callback_data="enter_promocode")
    kb.button(text="✅ Подтвердить заказ", callback_data=f"confirm_order_{order_id}")
    kb.button(text="❌ Отмена", callback_data="back_to_main")
    kb.adjust(1)
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML", disable_web_page_preview=True)
    await state.set_state(OrderState.waiting_confirm)

# ====== ПРОМОКОДЫ ======
@dp.callback_query(F.data == "enter_promocode")
async def enter_promocode(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("Введите промокод:")
    await state.set_state(OrderState.waiting_promocode)

@dp.message(OrderState.waiting_promocode)
async def apply_promocode(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    promo = await database.get_promocode(code)
    if not promo:
        return await message.answer("❌ Промокод не найден.")
    if promo[3] and promo[2] >= promo[3]:
        return await message.answer("❌ Промокод уже использован максимальное количество раз.")
    data = await state.get_data()
    price = data['price']
    discount = promo[1]
    new_price = price * (1 - discount/100.0)
    await state.update_data(promocode=code, price=new_price, discount=discount)
    await message.answer(f"✅ Промокод применён! Скидка {discount}%. Новая цена: {new_price:.2f} руб.")
    # Возвращаем к подтверждению
    order_id = data['order_id']
    service_desc = data.get('service_name', 'Услуга')
    if data.get('subtype'):
        service_desc += f" ({data['subtype']})"
    text = f"""
<b>Подтвердите заказ</b>

🆔 Номер заказа: {order_id}
📦 Услуга: {service_desc}
🔢 Количество: {data['quantity']}
💰 Цена (со скидкой): {new_price:.2f} руб.
🔗 Ссылка: {data['link']}
"""
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить заказ", callback_data=f"confirm_order_{order_id}")
    kb.button(text="❌ Отмена", callback_data="back_to_main")
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML", disable_web_page_preview=True)
    await state.set_state(OrderState.waiting_confirm)

# ====== ПОДТВЕРЖДЕНИЕ ЗАКАЗА ======
@dp.callback_query(F.data.startswith("confirm_order_"))
async def confirm_order(call: CallbackQuery, state: FSMContext):
    await call.answer()
    order_id = call.data.split("_")[2]
    data = await state.get_data()
    if data.get('order_id') != order_id:
        await call.message.answer("Ошибка: заказ не найден.")
        return

    # Списываем средства
    balance = await database.get_balance(call.from_user.id)
    if balance < data['price']:
        await call.message.answer("❌ Недостаточно средств. Пополните баланс.")
        return
    await database.update_balance(call.from_user.id, -data['price'])

    # Сохраняем заказ в БД
    service_desc = data.get('service_name', 'Услуга')
    if data.get('subtype'):
        service_desc += f" ({data['subtype']})"

    await database.create_order(
        order_id=order_id,
        user_id=call.from_user.id,
        service_id=0,
        quantity=data['quantity'],
        price=data['price'],
        link=data['link'],
        status="PAID",
        comment=service_desc,
        promocode=data.get('promocode')
    )

    new_balance = balance - data['price']
    await call.message.edit_text(
        f"✅ Заказ №{order_id} успешно оформлен!\n\n"
        f"📦 Услуга: {service_desc}\n"
        f"🔢 Количество: {data['quantity']}\n"
        f"💰 Сумма: {data['price']:.2f} руб.\n"
        f"🔗 Ссылка: {data['link']}\n\n"
        f"💰 Новый баланс: {new_balance:.2f} руб.\n\n"
        "Ваш заказ передан в работу. Ожидайте выполнения."
    )

    admins = await database.get_all_admins()
    for admin in admins:
        try:
            await bot.send_message(
                admin,
                f"📦 Новый заказ №{order_id} от {call.from_user.id}\n"
                f"Услуга: {service_desc}\n"
                f"Количество: {data['quantity']}\n"
                f"Сумма: {data['price']:.2f} руб.\n"
                f"Ссылка: {data['link']}"
            )
        except Exception as e:
            logging.error(f"Failed to notify admin {admin}: {e}")

    await state.clear()

# ====== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ АДМИНОВ ======
async def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

async def is_admin_from_db_or_config(user_id: int) -> bool:
    if user_id in STATIC_ADMINS:
        return True
    return await database.is_admin(user_id)

# ====== УПРАВЛЕНИЕ БАЛАНСОМ (для владельца) ======
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

# ====== УПРАВЛЕНИЕ ПРОМОКОДАМИ (только владелец) ======
@dp.message(Command("addpromo"))
async def add_promo(message: Message, state: FSMContext):
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
        await database.add_promocode(code, discount, max_uses)
        await message.answer(f"✅ Промокод {code} создан! Скидка: {discount}%, макс. использований: {max_uses or '∞'}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

# ====== УПРАВЛЕНИЕ ЦЕНАМИ (только владелец) ======
@dp.message(Command("setprice"))
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
    await database.update_service_price(service_id, price)
    await message.answer(f"Цена услуги #{service_id} установлена на {price:.2f} руб.")

@dp.message(Command("setpriceall"))
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
    await database.update_all_prices(discount)
    await message.answer(f"✅ Все цены изменены на {discount}% {'(скидка)' if discount > 0 else '(повышение)' if discount < 0 else '(без изменений)'}")

# ====== УПРАВЛЕНИЕ СКОРОСТЬЮ НАКРУТКИ ======
@dp.message(Command("setstat"))
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
    await database.update_service_speed(service_id, speed)
    speed_text = {1: "быстро", 2: "умеренно", 3: "медленно"}.get(speed)
    await message.answer(f"Скорость услуги #{service_id} установлена: {speed_text}")

# ====== УПРАВЛЕНИЕ ТЕКСТОМ УСЛУГИ ======
@dp.message(Command("settext"))
async def set_text(message: Message, state: FSMContext):
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
    await database.update_service_description(service_id, text)
    await message.answer(f"Текст услуги #{service_id} обновлён.")

# ====== УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ ======
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

# ====== УПРАВЛЕНИЕ ЗАКАЗАМИ ======
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

# ====== УПРАВЛЕНИЕ БОТОМ ======
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

# ====== УПРАВЛЕНИЕ АДМИНАМИ ======
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

@dp.message(Command("admins"))
async def list_admins(message: Message):
    if not await is_owner(message.from_user.id):
        return
    admins = await database.get_all_admins()
    if not admins:
        await message.answer("Список администраторов пуст.")
        return
    text = "👑 <b>Список администраторов:</b>\n"
    for admin_id in admins:
        text += f"- {admin_id}\n"
    await message.answer(text, parse_mode="HTML")

# ====== СТАТИСТИКА ======
@dp.message(Command("statsbot"))
async def stats_bot(message: Message):
    if not await is_owner(message.from_user.id):
        return
    users_count = await database.get_user_count()
    orders_count = await database.get_completed_orders()
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0)
    week_start = now - timedelta(days=now.weekday())
    month_start = datetime(now.year, now.month, 1, 0, 0, 0)
    revenue_today = await database.get_revenue(today_start, now)
    revenue_week = await database.get_revenue(week_start, now)
    revenue_month = await database.get_revenue(month_start, now)
    revenue_all = await database.get_revenue(datetime(2020, 1, 1), now)
    admins = await database.get_all_admins()
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

# ====== РАССЫЛКА ======
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

# ====== КОМАНДЫ ПОМОЩИ ======
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

@dp.message(Command("helpowner"))
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

# ====== ДИАГНОСТИКА ======
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

# ====== КАЛЬКУЛЯТОР, ТЕХПОДДЕРЖКА, FAQ ======
@dp.callback_query(F.data == "calc")
async def calc_menu(call: CallbackQuery):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    text = """
<b>Калькулятор стоимости</b>

Пока в разработке. Скоро здесь будет расчёт стоимости для всех услуг.
"""
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Вернуться назад", callback_data="back_to_main")
    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "support")
async def support(call: CallbackQuery):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Вернуться назад", callback_data="back_to_main")
    text = """
<b>Имеются вопросы, хотите предложить идею или у вас возникла проблема</b><tg-emoji emoji-id="5386713103213814186">❕</tg-emoji><b>

</b><blockquote><b>Напишите нам в Telegram: @nBoost_supports </b><tg-emoji emoji-id="5386748326240611247">✅</tg-emoji></blockquote>

<b>Ответ поступает в течение 24 часов</b><tg-emoji emoji-id="5386713103213814186">❕</tg-emoji>
    """
    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "faq")
async def faq(call: CallbackQuery):
    await call.answer()
    if await check_ban_and_terms(call.from_user.id):
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Вернуться назад", callback_data="back_to_main")
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
    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

# ====== ЗАПУСК ======
async def main():
    await database.init_db()
    for admin_id in STATIC_ADMINS:
        await database.add_admin(admin_id)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())