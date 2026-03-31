from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from bot_instance import bot

from states.states import OrderState
import database as db
from keyboards import get_platform_keyboard, get_telegram_menu, get_vk_menu, get_instagram_menu, get_tiktok_menu, get_stars_menu
from utils.helpers import generate_order_id, validate_link
import settings

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "order")
async def order_menu(call: CallbackQuery):
    await call.answer()
    kb = get_platform_keyboard()
    await call.message.edit_text("<b>Выберите платформу для накрутки</b>", reply_markup=kb, parse_mode="HTML")

# Telegram
@router.callback_query(F.data == "platform_telegram")
async def telegram_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    kb = get_telegram_menu()
    await call.message.edit_text("<b>Выберите услугу для Telegram</b>", reply_markup=kb, parse_mode="HTML")

# Подуслуги Telegram: просмотры, подписчики, реакции, дополнительно, старты
# Для простоты пока оставим структуру, но можно вынести в отдельные обработчики
@router.callback_query(F.data == "tg_views")
async def tg_views(call: CallbackQuery, state: FSMContext):
    await call.answer()
    # service_id можно получить из БД по имени, но пока используем временный подход
    service = await db.get_services_by_subcategory("telegram", "views", None)
    if not service:
        await call.message.answer("Услуга временно недоступна.")
        return
    await state.update_data(service_id=service[0][0])  # берем id
    await call.message.answer(f"Услуга: {service[0][4]}\nВведите количество (минимум 1):")
    await state.set_state(OrderState.waiting_quantity)

# ... аналогично для остальных подуслуг

@router.message(OrderState.waiting_quantity)
async def quantity_input(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Введите число!")
    quantity = int(message.text)
    data = await state.get_data()
    service = await db.get_service(data['service_id'])
    if not service:
        await message.answer("Ошибка: услуга не найдена.")
        await state.clear()
        return
    min_q, max_q = service[8], service[9]  # индексы зависят от структуры
    if quantity < min_q or (max_q and quantity > max_q):
        return await message.answer(f"Количество должно быть от {min_q} до {max_q}.")
    price = quantity * service[5]  # цена
    await state.update_data(quantity=quantity, price=price)
    await message.answer(f"💰 Стоимость: {price:.2f} руб.\n\nОтправьте ссылку:")
    await state.set_state(OrderState.waiting_link)

@router.message(OrderState.waiting_link)
async def link_input(message: Message, state: FSMContext):
    link = message.text.strip()
    if not validate_link(link):
        return await message.answer("Пожалуйста, отправьте корректную ссылку, начинающуюся с http:// или https://")
    data = await state.get_data()
    order_id = generate_order_id()
    await state.update_data(link=link, order_id=order_id)

    balance = await db.get_balance(message.from_user.id)
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

    # Показать подтверждение с промокодом
    await show_confirmation(message, state, order_id)

async def show_confirmation(message: Message, state: FSMContext, order_id: str):
    data = await state.get_data()
    service = await db.get_service(data['service_id'])
    text = f"""
<b>Подтвердите заказ</b>

🆔 Номер заказа: {order_id}
📦 Услуга: {service[4]}
🔢 Количество: {data['quantity']}
💰 Цена: {data['price']:.2f} руб.
🔗 Ссылка: {data['link']}
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="🎁 Ввести промокод", callback_data="enter_promocode")
    kb.button(text="✅ Подтвердить заказ", callback_data=f"confirm_order_{order_id}")
    kb.button(text="❌ Отмена", callback_data="back_to_main")
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await state.set_state(OrderState.waiting_confirm)

@router.callback_query(F.data == "enter_promocode")
async def enter_promocode(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("Введите промокод:")
    await state.set_state(OrderState.waiting_promocode)

@router.message(OrderState.waiting_promocode)
async def apply_promocode(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    promo = await db.get_promocode(code)
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
    await show_confirmation(message, state, data['order_id'])

@router.callback_query(F.data.startswith("confirm_order_"))
async def confirm_order(call: CallbackQuery, state: FSMContext):
    await call.answer()
    order_id = call.data.split("_")[2]
    data = await state.get_data()
    if data.get('order_id') != order_id:
        await call.message.answer("Ошибка: заказ не найден.")
        return

    balance = await db.get_balance(call.from_user.id)
    if balance < data['price']:
        await call.message.answer("❌ Недостаточно средств. Пополните баланс.")
        return
    await db.update_balance(call.from_user.id, -data['price'])

    service = await db.get_service(data['service_id'])
    service_name = service[4]
    if data.get('subtype'):
        service_name += f" ({data['subtype']})"

    await db.create_order(
        order_id=order_id,
        user_id=call.from_user.id,
        service_id=data['service_id'],
        quantity=data['quantity'],
        price=data['price'],
        link=data['link'],
        status="PAID",
        comment=service_name,
        promocode=data.get('promocode')
    )

    new_balance = balance - data['price']
    await call.message.edit_text(
        f"✅ Заказ №{order_id} успешно оформлен!\n\n"
        f"📦 Услуга: {service_name}\n"
        f"🔢 Количество: {data['quantity']}\n"
        f"💰 Сумма: {data['price']:.2f} руб.\n"
        f"🔗 Ссылка: {data['link']}\n\n"
        f"💰 Новый баланс: {new_balance:.2f} руб.\n\n"
        "Ваш заказ передан в работу. Ожидайте выполнения."
    )

    admins = await db.get_all_admins()
    for admin in admins:
        try:
            await bot.send_message(
                admin,
                f"📦 Новый заказ №{order_id} от {call.from_user.id}\n"
                f"Услуга: {service_name}\n"
                f"Количество: {data['quantity']}\n"
                f"Сумма: {data['price']:.2f} руб.\n"
                f"Ссылка: {data['link']}"
            )
        except:
            pass

    await state.clear()