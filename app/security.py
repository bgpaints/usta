"""Пароли, SMS-коды, токены, нормализация телефонов, проверка входа из Telegram."""
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import timedelta
from typing import Optional
from urllib.parse import parse_qsl

import jwt

from .config import settings
from .db import utcnow

# ---------- Пароли сотрудников (scrypt, без внешних зависимостей) ----------

_SCRYPT = dict(n=2**14, r=8, p=1, dklen=32)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
    return hmac.compare_digest(digest.hex(), digest_hex)


# ---------- SMS-коды ----------

def new_otp() -> str:
    return f"{secrets.randbelow(10000):04d}"


def hash_otp(phone: str, code: str) -> str:
    return hmac.new(settings.jwt_secret.encode(), f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


# ---------- Телефоны: Казахстан (+7) и Узбекистан (+998) ----------

def normalize_phone(raw: str) -> Optional[str]:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits[0] in "78":
        digits = "7" + digits[1:]
    elif len(digits) == 10 and digits[0] == "7":
        digits = "7" + digits
    if len(digits) == 11 and digits.startswith("7"):
        return "+" + digits
    if len(digits) == 12 and digits.startswith("998"):
        return "+" + digits
    return None


# ---------- Токены ----------

def make_token(subject: int, kind: str, role: Optional[str] = None) -> str:
    if kind == "master":
        exp = utcnow() + timedelta(days=settings.master_token_days)
    else:
        exp = utcnow() + timedelta(hours=settings.staff_token_hours)
    payload = {"sub": str(subject), "typ": kind, "exp": exp}
    if role:
        payload["role"] = role
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def read_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


# ---------- Telegram Mini App ----------

def verify_telegram_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> Optional[dict]:
    """Проверяет подпись initData, которую Telegram передаёт в mini-app.
    Возвращает данные пользователя Telegram или None, если подпись неверна/устарела."""
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received_hash):
        return None
    auth_date = int(pairs.get("auth_date", "0"))
    if time.time() - auth_date > max_age_seconds:
        return None
    user = json.loads(pairs.get("user", "{}"))
    return user or None
