"""Таблицы базы данных платформы Usta.

Главные цепочки:
  Партия кодов -> Код -> (Отгрузка дилеру) -> Скан мастером -> Запись в журнале баллов
  Мастер -> Заявка на награду -> Списание баллов
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow


# ---------- Мастера и вход ----------

class Master(Base):
    __tablename__ = "masters"
    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # главный ключ мастера
    name: Mapped[Optional[str]] = mapped_column(String(120))
    city: Mapped[Optional[str]] = mapped_column(String(80))
    specialization: Mapped[Optional[str]] = mapped_column(String(40))  # interior / facade / waterproofing / team
    telegram_id: Mapped[Optional[str]] = mapped_column(String(40), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active / blocked
    manual_blocked_until: Mapped[Optional[datetime]] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class OtpCode(Base):
    __tablename__ = "otp_codes"
    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    code_hash: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column()
    attempts: Mapped[int] = mapped_column(default=0)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


# ---------- Справочники ----------

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(40))  # interior / facade / waterproofing
    volume: Mapped[float] = mapped_column(Float)        # 18
    unit: Mapped[str] = mapped_column(String(10))       # л / кг
    points_per_unit: Mapped[int] = mapped_column(Integer)  # баллов за литр/кг
    multiplier: Mapped[float] = mapped_column(Float, default=1.0)  # акция, например x2
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Dealer(Base):
    __tablename__ = "dealers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    city: Mapped[str] = mapped_column(String(80))
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lng: Mapped[Optional[float]] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------- Коды ----------

class CodeBatch(Base):
    __tablename__ = "code_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    source: Mapped[str] = mapped_column(String(30))  # asian_paints / bgp
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("staff.id"))


class Code(Base):
    __tablename__ = "codes"
    id: Mapped[int] = mapped_column(primary_key=True)
    value: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("code_batches.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    # loaded -> activated (отгружен дилеру) -> scanned (мастер получил баллы); void — аннулирован
    status: Mapped[str] = mapped_column(String(20), default="loaded", index=True)
    shipment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shipments.id"), index=True)
    dealer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("dealers.id"), index=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column()
    scanned_at: Mapped[Optional[datetime]] = mapped_column()
    scanned_by: Mapped[Optional[int]] = mapped_column(ForeignKey("masters.id"), index=True)
    scan_lat: Mapped[Optional[float]] = mapped_column(Float)
    scan_lng: Mapped[Optional[float]] = mapped_column(Float)

    product: Mapped[Product] = relationship()
    dealer: Mapped[Optional[Dealer]] = relationship()


class Shipment(Base):
    __tablename__ = "shipments"
    id: Mapped[int] = mapped_column(primary_key=True)
    dealer_id: Mapped[int] = mapped_column(ForeignKey("dealers.id"), index=True)
    note: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("staff.id"))


class ScanAttempt(Base):
    """Каждая попытка скана, удачная или нет — для антифрода и аналитики."""
    __tablename__ = "scan_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id"), index=True)
    code_value: Mapped[str] = mapped_column(String(64))
    manual: Mapped[bool] = mapped_column(Boolean, default=False)
    success: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str] = mapped_column(String(40))
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lng: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


# ---------- Баллы ----------

class LedgerEntry(Base):
    """Журнал баллов. Баланс мастера = сумма его записей. Записи никогда не удаляются."""
    __tablename__ = "ledger"
    id: Mapped[int] = mapped_column(primary_key=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id"), index=True)
    # scan / bonus / redeem / refund / expire / adjust / reversal
    kind: Mapped[str] = mapped_column(String(20))
    points: Mapped[int] = mapped_column(Integer)
    code_id: Mapped[Optional[int]] = mapped_column(ForeignKey("codes.id"))
    redemption_id: Mapped[Optional[int]] = mapped_column(ForeignKey("redemptions.id"))
    available_at: Mapped[Optional[datetime]] = mapped_column()  # до этой даты нельзя тратить
    expires_at: Mapped[Optional[datetime]] = mapped_column()
    frozen: Mapped[bool] = mapped_column(Boolean, default=False)  # заморожено проверкой фрода
    note: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)

    __table_args__ = (Index("ix_ledger_master_kind", "master_id", "kind"),)


# ---------- Награды ----------

class Reward(Base):
    __tablename__ = "rewards"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[Optional[str]] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20))  # cash / product / trip
    cost_points: Mapped[int] = mapped_column(Integer)
    min_level: Mapped[Optional[str]] = mapped_column(String(20))
    stock: Mapped[Optional[int]] = mapped_column(Integer)  # None — без ограничения
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Redemption(Base):
    __tablename__ = "redemptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id"), index=True)
    reward_id: Mapped[int] = mapped_column(ForeignKey("rewards.id"))
    points: Mapped[int] = mapped_column(Integer)
    # pending -> approved -> done; или rejected (баллы возвращаются)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    processed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("staff.id"))
    processed_at: Mapped[Optional[datetime]] = mapped_column()
    comment: Mapped[Optional[str]] = mapped_column(String(255))

    reward: Mapped[Reward] = relationship()
    master: Mapped[Master] = relationship()


# ---------- Фрод ----------

class FraudFlag(Base):
    __tablename__ = "fraud_flags"
    id: Mapped[int] = mapped_column(primary_key=True)
    master_id: Mapped[Optional[int]] = mapped_column(ForeignKey("masters.id"), index=True)
    code_value: Mapped[Optional[str]] = mapped_column(String(64))
    # not_activated / foreign_code / daily_limit / burst / manual_bruteforce
    kind: Mapped[str] = mapped_column(String(40))
    detail: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open / released / confirmed
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    resolved_by: Mapped[Optional[int]] = mapped_column(ForeignKey("staff.id"))
    resolved_at: Mapped[Optional[datetime]] = mapped_column()


# ---------- Сотрудники и журнал действий ----------

class Staff(Base):
    __tablename__ = "staff"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))  # admin / marketing / warehouse / finance
    password_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[Optional[int]] = mapped_column(ForeignKey("staff.id"), index=True)
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[Optional[str]] = mapped_column(String(40))
    entity_id: Mapped[Optional[int]] = mapped_column(Integer)
    detail: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
