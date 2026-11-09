"""Баллы: баланс, доступно к обмену, уровни, сгорание."""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import utcnow
from ..models import LedgerEntry, Master

def add_entry(db: Session, master_id: int, kind: str, points: int, *, code_id: Optional[int] = None,
              redemption_id: Optional[int] = None, frozen: bool = False, note: Optional[str] = None,
              now: Optional[datetime] = None) -> LedgerEntry:
    now = now or utcnow()
    entry = LedgerEntry(master_id=master_id, kind=kind, points=points, code_id=code_id,
                        redemption_id=redemption_id, frozen=frozen, note=note, created_at=now)
    if points > 0 and kind in ("scan", "bonus"):
        entry.available_at = now + timedelta(days=settings.points_hold_days)
        entry.expires_at = now + timedelta(days=settings.points_ttl_days)
    db.add(entry)
    return entry


def balance(db: Session, master_id: int) -> int:
    """Все не замороженные баллы на счёте."""
    q = select(func.coalesce(func.sum(LedgerEntry.points), 0)).where(
        LedgerEntry.master_id == master_id, LedgerEntry.frozen.is_(False))
    return int(db.scalar(q))


def pending(db: Session, master_id: int, now: Optional[datetime] = None) -> int:
    """Начислено, но ещё на удержании (нельзя обменять)."""
    now = now or utcnow()
    q = select(func.coalesce(func.sum(LedgerEntry.points), 0)).where(
        LedgerEntry.master_id == master_id, LedgerEntry.frozen.is_(False),
        LedgerEntry.points > 0, LedgerEntry.available_at.is_not(None), LedgerEntry.available_at > now)
    return int(db.scalar(q))


def frozen_points(db: Session, master_id: int) -> int:
    q = select(func.coalesce(func.sum(LedgerEntry.points), 0)).where(
        LedgerEntry.master_id == master_id, LedgerEntry.frozen.is_(True))
    return int(db.scalar(q))


def available(db: Session, master_id: int, now: Optional[datetime] = None) -> int:
    return max(0, balance(db, master_id) - pending(db, master_id, now))


def earned_last_year(db: Session, master_id: int, now: Optional[datetime] = None) -> int:
    now = now or utcnow()
    q = select(func.coalesce(func.sum(LedgerEntry.points), 0)).where(
        LedgerEntry.master_id == master_id, LedgerEntry.kind.in_(("scan", "bonus")),
        LedgerEntry.frozen.is_(False), LedgerEntry.points > 0,
        LedgerEntry.created_at >= now - timedelta(days=365))
    return int(db.scalar(q))


def level_info(earned: int) -> dict:
    levels = settings.levels
    idx = 0
    for i, (_, minimum) in enumerate(levels):
        if earned >= minimum:
            idx = i
    name, minimum = levels[idx]
    nxt = levels[idx + 1] if idx + 1 < len(levels) else None
    return {
        "level": name,
        "earned_12m": earned,
        "next_level": nxt[0] if nxt else None,
        "points_to_next": (nxt[1] - earned) if nxt else 0,
        "progress_pct": 100 if not nxt else int((earned - minimum) * 100 / (nxt[1] - minimum)),
    }


def level_rank(name: Optional[str]) -> int:
    names = [n for n, _ in settings.levels]
    return names.index(name) if name in names else 0


def expire_points(db: Session, master: Master, now: Optional[datetime] = None) -> int:
    """Сгорание баллов по принципу «сначала тратятся самые старые».
    Сгорает: (заработано с истёкшим сроком) − (уже потрачено) − (уже сгорело), если > 0."""
    now = now or utcnow()
    db.flush()  # учесть записи, добавленные в этой же сессии
    expired_earn = db.scalar(select(func.coalesce(func.sum(LedgerEntry.points), 0)).where(
        LedgerEntry.master_id == master.id, LedgerEntry.points > 0, LedgerEntry.frozen.is_(False),
        LedgerEntry.expires_at.is_not(None), LedgerEntry.expires_at <= now))
    spent = -db.scalar(select(func.coalesce(func.sum(LedgerEntry.points), 0)).where(
        LedgerEntry.master_id == master.id, LedgerEntry.points < 0, LedgerEntry.kind != "expire"))
    refunded = db.scalar(select(func.coalesce(func.sum(LedgerEntry.points), 0)).where(
        LedgerEntry.master_id == master.id, LedgerEntry.kind == "refund"))
    spent = int(spent) - int(refunded)
    already = -db.scalar(select(func.coalesce(func.sum(LedgerEntry.points), 0)).where(
        LedgerEntry.master_id == master.id, LedgerEntry.kind == "expire"))
    to_expire = int(expired_earn) - int(spent) - int(already)
    to_expire = min(to_expire, balance(db, master.id))
    if to_expire > 0:
        add_entry(db, master.id, "expire", -to_expire, note="Срок действия баллов истёк", now=now)
        return to_expire
    return 0
