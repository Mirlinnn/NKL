import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot_instance import bot
from config import OWNER_ID, PHOTO_PATH
from keyboards import get_main_keyboard
import database as db
import logging

router = Router()
logger = logging.getLogger(__name__)

# ... (остальные функции is_bot_available, check_ban_and_terms)

async def show_main_menu(chat_id: int):
    balance = await db.get_balance(chat_id)
    text = f"""
<b>Приветствую!</b> <tg-emoji emoji-id="5877700484453634587">✈️</tg-emoji>
<b>Добро пожаловать в бота для накрутки статистики пользователей, просмотров и реакций

</b><blockquote><tg-emoji emoji-id="5870994129244131212">👤</tg-emoji> <b>Тех.поддержка: </b>@nBoost_supports<b>
</b><tg-emoji emoji-id="5870995486453796729">📊</tg-emoji> <b>Наш канал: </b>@channel_username</blockquote>
<a href="https://t.me/your_offer_link">Договор оферты</a> • <a href="https://t.me/your_terms_link">Пользовательское соглашение</a>

<b>💰 Ваш баланс: {balance:.2f} руб.</b>
    """
    kb = get_main_keyboard()
    if os.path.exists(PHOTO_PATH):
        try:
            photo = FSInputFile(PHOTO_PATH)
            await bot.send_photo(chat_id, photo, caption=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)

# ... (хендлеры)