from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
import base64
import hashlib
import json
import aiohttp
import uuid
from bot_instance import bot

from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, YOOKASSA_RETURN_URL
from config import HELEKET_MERCHANT_ID, HELEKET_API_KEY, HELEKET_API_URL, HELEKET_RETURN_URL
import database as db
from utils.helpers import is_owner, is_admin_from_db_or_config

router = Router()
logger = logging.getLogger(__name__)

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
            logger.info(f"YooKassa response: {resp.status} {response_text}")
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

# ====== Heleket ======
def generate_heleket_sign(data: dict, api_key: str) -> str:
    json_data = json.dumps(data, separators=(',', ':'))
    base64_data = base64.b64encode(json_data.encode()).decode()
    return hashlib.md5((base64_data + api_key).encode()).hexdigest()

async def create_heleket_payment(amount: float, order_id: str, description: str, user_id: int):
    """
    Создаёт платёж через Heleket с конвертацией RUB -> USDT.
    amount – сумма в рублях.
    """
    payload = {
        "amount": f"{amount:.2f}",
        "currency": "RUB",           # фиатная валюта счёта
        "to_currency": "RUB",       # криптовалюта для оплаты
        "order_id": order_id,
        # "course_source": "Binance", # опционально: источник курса
    }
    # Сортируем ключи для стабильной подписи
    sorted_payload = {k: payload[k] for k in sorted(payload.keys())}
    json_data = json.dumps(sorted_payload, separators=(',', ':'))
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
        async with session.post(f"{HELEKET_API_URL}/payment", headers=headers, data=json_data) as resp:
            response_text = await resp.text()
            logger.info(f"Heleket response: {resp.status} {response_text}")
            if resp.status != 200:
                raise Exception(f"Heleket HTTP error {resp.status}: {response_text}")
            response_json = json.loads(response_text)
            if response_json.get('state') != 0:
                raise Exception(f"Heleket error: {response_json}")
            return response_json['result']   # содержит uuid, url, payer_amount, payer_currency и др.

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
                logger.error(f"Heleket payment info error: HTTP {resp.status}")
                return None
            response_json = await resp.json()
            if response_json.get('state') != 0:
                logger.error(f"Heleket payment info error: {response_json}")
                return None
            return response_json['result'].get('payment_status')
