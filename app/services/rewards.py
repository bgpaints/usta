"""Обмен баллов на награды и обработка заявок."""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import FraudFlag, LedgerEntry, Master, Redemption, Reward
from . import ledger


class RewardError(Exception):
    pass


def redeem(db: Session, master: Master, reward: Reward) -> Redemption:
    if master.status != "active":
        raise RewardError("Аккаунт заблокирован")
    if not reward.active:
        raise RewardError("Награда недоступна")
    if reward.stock is not None and reward.stock <= 0:
        raise RewardError("Награда закончилась")
    open_flags = db.scalar(select(FraudFlag.id).where(
        FraudFlag.master_id == master.id, FraudFlag.status == "open").limit(1))
    if open_flags:
        raise RewardError("Обмен временно недоступен: идёт проверка начислений")
    if reward.min_level:
        current = ledger.level_info(ledger.earned_last_year(db, master.id))["level"]
        if ledger.level_rank(current) < ledger.level_rank(reward.min_level):
            raise RewardError(f"Доступно с уровня «{reward.min_level}»")
    if ledger.available(db, master.id) < reward.cost_points:
        raise RewardError("Недостаточно баллов")
    red = Redemption(master_id=master.id, reward_id=reward.id, points=reward.cost_points)
    db.add(red)
    db.flush()
    ledger.add_entry(db, master.id, "redeem", -reward.cost_points, redemption_id=red.id, note=reward.title)
    if reward.stock is not None:
        reward.stock -= 1
    return red


ALLOWED = {"pending": {"approved", "rejected"}, "approved": {"done", "rejected"}}


def process(db: Session, red: Redemption, new_status: str, staff_id: int, comment: Optional[str] = None) -> Redemption:
    if new_status not in ALLOWED.get(red.status, set()):
        raise RewardError(f"Нельзя перевести заявку из «{red.status}» в «{new_status}»")
    red.status, red.processed_by, red.processed_at, red.comment = new_status, staff_id, utcnow(), comment
    if new_status == "rejected":
        ledger.add_entry(db, red.master_id, "refund", red.points, redemption_id=red.id,
                         note=f"Возврат: {red.reward.title}")
        if red.reward.stock is not None:
            red.reward.stock += 1
    return red


def resolve_flag(db: Session, flag: FraudFlag, decision: str, staff_id: int) -> FraudFlag:
    """released — разморозить баллы мастера; confirmed — баллы остаются замороженными навсегда."""
    if flag.status != "open":
        raise RewardError("Проверка уже закрыта")
    if decision not in ("released", "confirmed"):
        raise RewardError("Решение: released или confirmed")
    flag.status, flag.resolved_by, flag.resolved_at = decision, staff_id, utcnow()
    if flag.master_id:
        others_open = db.scalar(select(FraudFlag.id).where(
            FraudFlag.master_id == flag.master_id, FraudFlag.status == "open", FraudFlag.id != flag.id).limit(1))
        if decision == "released" and not others_open:
            for e in db.scalars(select(LedgerEntry).where(
                    LedgerEntry.master_id == flag.master_id, LedgerEntry.frozen.is_(True),
                    LedgerEntry.note.is_not(None), ~LedgerEntry.note.like("[отменено]%"))):
                e.frozen = False
        elif decision == "confirmed":
            for e in db.scalars(select(LedgerEntry).where(
                    LedgerEntry.master_id == flag.master_id, LedgerEntry.frozen.is_(True))):
                if not (e.note or "").startswith("[отменено]"):
                    e.note = f"[отменено] {e.note or ''}".strip()
    return flag
