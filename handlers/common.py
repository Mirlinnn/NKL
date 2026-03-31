from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
import logging
from bot_instance import bot

from states.states import OrderState
from keyboards import get_back_keyboard
from utils.helpers import is_admin_from_db_or_config

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "back_to_main")
async def back_to_main(call: CallbackQuery):
    await call.answer()
    # Импортируем функцию показа главного меню (чтобы избежать циклического импорта)
    from handlers.start import show_main_menu
    try:
        await call.message.delete()
    except:
        pass
    await show_main_menu(call.from_user.id)

@router.message(Command("help"))
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

@router.message(Command("checkpay"))
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
    txs = await db.get_transactions(user_id, 20)
    if not txs:
        await message.answer(f"У пользователя {user_id} нет транзакций.")
        return
    text = f"📜 История транзакций пользователя {user_id} (последние 20):\n"
    for tx in txs:
        status_emoji = "✅" if tx[4] == "success" else "❌"
        text += f"{status_emoji} {tx[6][:10]} {tx[2]:+.2f} руб. ({tx[3]})\n"
    await message.answer(text)

@router.message(Command("fixdb"))
async def fixdb_command(message: Message):
    if not await is_admin_from_db_or_config(message.from_user.id):
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

@router.callback_query(F.data == "calc")
async def calc_menu(call: CallbackQuery):
    await call.answer()
    text = """
<b>Калькулятор стоимости</b>

Пока в разработке. Скоро здесь будет расчёт стоимости для всех услуг.
"""
    kb = get_back_keyboard()
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "support")
async def support(call: CallbackQuery):
    await call.answer()
    text = """
<b>Имеются вопросы, хотите предложить идею или у вас возникла проблема</b><tg-emoji emoji-id="5386713103213814186">❕</tg-emoji><b>

</b><blockquote><b>Напишите нам в Telegram: @nBoost_supports </b><tg-emoji emoji-id="5386748326240611247">✅</tg-emoji></blockquote>

<b>Ответ поступает в течение 24 часов</b><tg-emoji emoji-id="5386713103213814186">❕</tg-emoji>
    """
    kb = get_back_keyboard()
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "faq")
async def faq(call: CallbackQuery):
    await call.answer()
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
    kb = get_back_keyboard()
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")