from aiogram.fsm.state import StatesGroup, State

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
    waiting_text = State()  # ← убрать точку после State()