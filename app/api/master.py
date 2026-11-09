"""API приложения мастера: профиль, скан, история, награды."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import LedgerEntry, Master, Redemption, Reward
from ..services import codes, ledger, rewards
from .deps import current_master

router = APIRouter(tags=["Приложение мастера"])

KIND_TITLES = {"scan": "Скан", "bonus": "Бонус", "redeem": "Обмен", "refund": "Возврат",
               "expire": "Сгорание", "adjust": "Корректировка"}


class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    city: Optional[str] = Field(default=None, max_length=80)
    specialization: Optional[Literal["interior", "facade", "waterproofing", "team"]] = None


class ScanBody(BaseModel):
    code: str = Field(max_length=300)
    manual: bool = False
    lat: Optional[float] = None
    lng: Optional[float] = None


def _profile(db: Session, m: Master) -> dict:
    return {
        "id": m.id, "phone": m.phone, "name": m.name, "city": m.city, "specialization": m.specialization,
        "balance": ledger.balance(db, m.id),
        "available": ledger.available(db, m.id),
        "pending": ledger.pending(db, m.id),
        "on_review": ledger.frozen_points(db, m.id) if _has_open_review(db, m) else 0,
        **ledger.level_info(ledger.earned_last_year(db, m.id)),
    }


def _has_open_review(db: Session, m: Master) -> bool:
    from ..models import FraudFlag
    return db.scalar(select(FraudFlag.id).where(FraudFlag.master_id == m.id, FraudFlag.status == "open").limit(1)) is not None


@router.get("/me")
def me(master: Master = Depends(current_master), db: Session = Depends(get_db)):
    return _profile(db, master)


@router.patch("/me")
def update_me(body: ProfileUpdate, master: Master = Depends(current_master), db: Session = Depends(get_db)):
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(master, k, v.strip() if isinstance(v, str) else v)
    db.commit()
    return _profile(db, master)


@router.post("/scan")
def scan(body: ScanBody, master: Master = Depends(current_master), db: Session = Depends(get_db)):
    result = codes.scan(db, master, body.code, manual=body.manual, lat=body.lat, lng=body.lng)
    db.commit()
    payload = result.__dict__ | {"balance": ledger.balance(db, master.id)}
    if not result.ok:
        raise HTTPException(status_code=409 if result.reason == "already_scanned" else 400, detail=payload)
    return payload


@router.get("/history")
def history(limit: int = 50, offset: int = 0, master: Master = Depends(current_master), db: Session = Depends(get_db)):
    rows = db.scalars(select(LedgerEntry).where(LedgerEntry.master_id == master.id)
                      .order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc())
                      .limit(min(limit, 200)).offset(offset))
    return [{"id": e.id, "kind": e.kind, "title": KIND_TITLES.get(e.kind, e.kind), "note": e.note,
             "points": e.points, "on_review": e.frozen, "created_at": e.created_at,
             "expires_at": e.expires_at} for e in rows]


@router.get("/rewards")
def list_rewards(master: Master = Depends(current_master), db: Session = Depends(get_db)):
    avail = ledger.available(db, master.id)
    level = ledger.level_info(ledger.earned_last_year(db, master.id))["level"]
    out = []
    for r in db.scalars(select(Reward).where(Reward.active.is_(True)).order_by(Reward.cost_points)):
        level_ok = not r.min_level or ledger.level_rank(level) >= ledger.level_rank(r.min_level)
        in_stock = r.stock is None or r.stock > 0
        out.append({"id": r.id, "title": r.title, "description": r.description, "kind": r.kind,
                    "cost_points": r.cost_points, "min_level": r.min_level, "in_stock": in_stock,
                    "can_redeem": level_ok and in_stock and avail >= r.cost_points,
                    "missing_points": max(0, r.cost_points - avail)})
    return out


@router.post("/rewards/{reward_id}/redeem")
def redeem(reward_id: int, master: Master = Depends(current_master), db: Session = Depends(get_db)):
    reward = db.get(Reward, reward_id)
    if reward is None:
        raise HTTPException(404, "Награда не найдена")
    try:
        red = rewards.redeem(db, master, reward)
    except rewards.RewardError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    db.commit()
    return {"redemption_id": red.id, "status": red.status, "balance": ledger.balance(db, master.id)}


@router.get("/redemptions")
def my_redemptions(master: Master = Depends(current_master), db: Session = Depends(get_db)):
    rows = db.scalars(select(Redemption).where(Redemption.master_id == master.id).order_by(Redemption.id.desc()))
    return [{"id": r.id, "reward": r.reward.title, "points": r.points, "status": r.status,
             "created_at": r.created_at, "comment": r.comment} for r in rows]
