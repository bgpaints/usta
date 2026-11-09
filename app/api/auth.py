"""Вход мастера по номеру телефона и SMS-коду."""
import hmac
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db, utcnow
from ..models import Master, OtpCode
from ..security import hash_otp, make_token, new_otp, normalize_phone
from ..sms import send_sms

router = APIRouter(prefix="/auth", tags=["Вход мастера"])


class OtpRequest(BaseModel):
    phone: str


class OtpVerify(BaseModel):
    phone: str
    code: str


@router.post("/otp/request")
def request_otp(body: OtpRequest, db: Session = Depends(get_db)):
    phone = normalize_phone(body.phone)
    if not phone:
        raise HTTPException(400, "Введите номер Казахстана (+7) или Узбекистана (+998)")
    hour_ago = utcnow() - timedelta(hours=1)
    sent = db.scalar(select(func.count()).select_from(OtpCode).where(
        OtpCode.phone == phone, OtpCode.created_at >= hour_ago))
    if sent >= settings.otp_max_per_hour:
        raise HTTPException(429, "Слишком много запросов. Попробуйте через час")
    code = new_otp()
    db.add(OtpCode(phone=phone, code_hash=hash_otp(phone, code),
                   expires_at=utcnow() + timedelta(minutes=settings.otp_ttl_minutes)))
    db.commit()
    send_sms(phone, f"Usta: ваш код {code}")
    resp = {"phone": phone, "sent": True}
    if settings.debug:
        resp["debug_code"] = code  # только в разработке
    return resp


@router.post("/otp/verify")
def verify_otp(body: OtpVerify, db: Session = Depends(get_db)):
    phone = normalize_phone(body.phone)
    if not phone:
        raise HTTPException(400, "Неверный номер")
    otp = db.scalars(select(OtpCode).where(OtpCode.phone == phone, OtpCode.used.is_(False))
                     .order_by(OtpCode.id.desc())).first()
    if otp is None or otp.expires_at < utcnow():
        raise HTTPException(400, "Код истёк. Запросите новый")
    if otp.attempts >= settings.otp_max_attempts:
        raise HTTPException(429, "Слишком много попыток. Запросите новый код")
    otp.attempts += 1
    if not hmac.compare_digest(otp.code_hash, hash_otp(phone, body.code.strip())):
        db.commit()
        raise HTTPException(400, "Неверный код")
    otp.used = True
    master = db.scalars(select(Master).where(Master.phone == phone)).first()
    is_new = master is None
    if is_new:
        master = Master(phone=phone)
        db.add(master)
    db.commit()
    if master.status != "active":
        raise HTTPException(403, "Аккаунт заблокирован")
    return {"token": make_token(master.id, "master"), "is_new": is_new or not master.name}
