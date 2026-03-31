from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from keyboards import get_back_keyboard

router = Router()

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
<b>Все частые вопросы которые задают пользователи❗️</b>

<blockquote expandable>1. Почему мою заявку на накрутку отклонили?
- Вашу заявку могли отклонить по некоторым причинам, все причины по которым вам могли отклонить заявку прописаны в пользовательском соглашении 

2. Я оплатил накрутку, но она так и не началась.
- Накрутка происходит в течении 24 часов, в эти 24 часа не входят услуги которые сами по себе Медленые

3. Почему так долго накручиваете?
- Причин может быть несколько, но основные причины что сервера нагружены, накрутка происходит в течение 24 часов после оплаты

4. Какие гарантии?
- Гарантия даётся на перод который указан в описании товара

5. Я заказал определённое количество накрутки, но пришло не все.
- Да, такое бывает, это называется "недокруты". Боты, которые не докрутили(сь), обычно в течении 24 все приходит, в эти 24 часа не входят услуги которые медленые сами по себе
</blockquote><b>Основные вопросы мы обговорили, в случае если у вас другой вопрос, то обращайтесь в службу поддержки бота:</b> @nBoost_supports
    """
    kb = get_back_keyboard()
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")