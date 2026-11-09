"""API админки BGP: справочники, коды, отгрузки, мастера, фрод, награды, выплаты, дашборд."""
import csv
import io
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (AuditLog, Code, CodeBatch, Dealer, FraudFlag, LedgerEntry, Master, Product, Redemption,
                      Reward, Staff)
from ..security import make_token, verify_password
from ..services import audit, codes, ledger, rewards
from .deps import current_staff, require

router = APIRouter(prefix="/admin", tags=["Админка"])


# ---------- Вход ----------

class LoginBody(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    staff = db.scalars(select(Staff).where(Staff.email == body.email.strip().lower())).first()
    if not staff or not staff.active or not verify_password(body.password, staff.password_hash):
        raise HTTPException(401, "Неверный email или пароль")
    audit.log(db, staff.id, "login")
    db.commit()
    return {"token": make_token(staff.id, "staff", staff.role), "role": staff.role, "name": staff.name}


@router.get("/me")
def whoami(staff: Staff = Depends(current_staff)):
    return {"id": staff.id, "email": staff.email, "name": staff.name, "role": staff.role}


# ---------- Продукты ----------

class ProductBody(BaseModel):
    sku: str = Field(max_length=60)
    name: str = Field(max_length=160)
    category: Literal["interior", "facade", "waterproofing", "other"]
    volume: float = Field(gt=0)
    unit: Literal["л", "кг"]
    points_per_unit: int = Field(ge=0)
    multiplier: float = Field(default=1.0, ge=0, le=10)
    active: bool = True


class ProductPatch(BaseModel):
    name: Optional[str] = None
    points_per_unit: Optional[int] = Field(default=None, ge=0)
    multiplier: Optional[float] = Field(default=None, ge=0, le=10)
    active: Optional[bool] = None


def _product(p: Product) -> dict:
    pts, calc = codes.points_for(p)
    return {"id": p.id, "sku": p.sku, "name": p.name, "category": p.category, "volume": p.volume, "unit": p.unit,
            "points_per_unit": p.points_per_unit, "multiplier": p.multiplier, "active": p.active,
            "points_per_can": pts, "calc": calc}


@router.get("/products")
def products(db: Session = Depends(get_db), _: Staff = Depends(current_staff)):
    return [_product(p) for p in db.scalars(select(Product).order_by(Product.name))]


@router.post("/products")
def create_product(body: ProductBody, db: Session = Depends(get_db), staff: Staff = Depends(require("products"))):
    if db.scalar(select(Product.id).where(Product.sku == body.sku)):
        raise HTTPException(400, "Такой SKU уже есть")
    p = Product(**body.model_dump())
    db.add(p)
    db.flush()
    audit.log(db, staff.id, "product.create", "product", p.id, sku=p.sku)
    db.commit()
    return _product(p)


@router.patch("/products/{pid}")
def patch_product(pid: int, body: ProductPatch, db: Session = Depends(get_db), staff: Staff = Depends(require("products"))):
    p = db.get(Product, pid)
    if not p:
        raise HTTPException(404, "Продукт не найден")
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(p, k, v)
    audit.log(db, staff.id, "product.update", "product", p.id, **changes)
    db.commit()
    return _product(p)


# ---------- Дилеры ----------

class DealerBody(BaseModel):
    name: str = Field(max_length=160)
    city: str = Field(max_length=80)
    lat: Optional[float] = None
    lng: Optional[float] = None


@router.get("/dealers")
def dealers(db: Session = Depends(get_db), _: Staff = Depends(current_staff)):
    return [{"id": d.id, "name": d.name, "city": d.city, "active": d.active}
            for d in db.scalars(select(Dealer).order_by(Dealer.name))]


@router.post("/dealers")
def create_dealer(body: DealerBody, db: Session = Depends(get_db), staff: Staff = Depends(require("products"))):
    d = Dealer(**body.model_dump())
    db.add(d)
    db.flush()
    audit.log(db, staff.id, "dealer.create", "dealer", d.id, name=d.name)
    db.commit()
    return {"id": d.id, "name": d.name, "city": d.city}


# ---------- Коды ----------

@router.post("/batches/import")
async def import_batch(name: str = Form(...), source: Literal["asian_paints", "bgp"] = Form("asian_paints"),
                       file: UploadFile = File(...), db: Session = Depends(get_db),
                       staff: Staff = Depends(require("codes"))):
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(400, "Файл больше 20 МБ, разбейте на части")
    try:
        rep = codes.import_codes_csv(db, content, name, source, staff.id)
    except codes.CodeError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    audit.log(db, staff.id, "batch.import", "batch", rep.batch_id, added=rep.added,
              duplicates=rep.duplicates, errors=len(rep.errors))
    db.commit()
    return {"batch_id": rep.batch_id, "added": rep.added, "duplicates": rep.duplicates,
            "errors": [{"row": r, "reason": m} for r, m in rep.errors[:200]], "errors_total": len(rep.errors)}


class GenerateBody(BaseModel):
    sku: str
    count: int = Field(gt=0, le=100_000)
    name: str


@router.post("/batches/generate")
def generate_batch(body: GenerateBody, db: Session = Depends(get_db), staff: Staff = Depends(require("codes"))):
    product = db.scalars(select(Product).where(Product.sku == body.sku)).first()
    if not product:
        raise HTTPException(400, "Неизвестный SKU")
    batch = codes.generate_codes(db, product, body.count, body.name, staff.id)
    audit.log(db, staff.id, "batch.generate", "batch", batch.id, sku=body.sku, count=body.count)
    db.commit()
    return {"batch_id": batch.id, "count": body.count}


@router.get("/batches")
def batches(db: Session = Depends(get_db), _: Staff = Depends(require("view"))):
    q = (select(CodeBatch, func.count(Code.id),
                func.sum(case((Code.status.in_(("activated", "scanned")), 1), else_=0)),
                func.sum(case((Code.status == "scanned", 1), else_=0)))
         .join(Code, Code.batch_id == CodeBatch.id, isouter=True).group_by(CodeBatch.id).order_by(CodeBatch.id.desc()))
    return [{"id": b.id, "name": b.name, "source": b.source, "created_at": b.created_at,
             "loaded": total, "activated": int(act or 0), "scanned": int(sc or 0)} for b, total, act, sc in db.execute(q)]


@router.get("/batches/{bid}/export.csv")
def export_batch(bid: int, db: Session = Depends(get_db), staff: Staff = Depends(require("codes"))):
    """Выгрузка кодов для печати наклеек."""
    rows = db.execute(select(Code.value, Product.sku).join(Product).where(Code.batch_id == bid).order_by(Code.id)).all()
    if not rows:
        raise HTTPException(404, "Партия пустая или не найдена")
    audit.log(db, staff.id, "batch.export", "batch", bid, count=len(rows))
    db.commit()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["code", "sku"])
    w.writerows(rows)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="batch-{bid}.csv"'})


# ---------- Отгрузки ----------

class ShipBody(BaseModel):
    dealer_id: int
    codes: list[str] = Field(min_length=1, max_length=50_000)
    note: Optional[str] = None


@router.post("/shipments")
def ship(body: ShipBody, db: Session = Depends(get_db), staff: Staff = Depends(require("ship"))):
    dealer = db.get(Dealer, body.dealer_id)
    if not dealer:
        raise HTTPException(400, "Дилер не найден")
    rep = codes.ship_codes(db, dealer, body.codes, staff.id, body.note)
    audit.log(db, staff.id, "shipment.create", "shipment", rep.shipment_id, dealer_id=dealer.id,
              activated=rep.activated, not_found=len(rep.not_found), already_used=len(rep.already_used))
    db.commit()
    return {"shipment_id": rep.shipment_id, "activated": rep.activated,
            "not_found": rep.not_found[:200], "already_used": rep.already_used[:200]}


# ---------- Мастера ----------

@router.get("/masters")
def masters(q: Optional[str] = None, limit: int = 50, offset: int = 0, db: Session = Depends(get_db),
            _: Staff = Depends(require("masters"))):
    stmt = select(Master).order_by(Master.id.desc()).limit(min(limit, 200)).offset(offset)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where((Master.phone.like(like)) | (Master.name.ilike(like)) | (Master.city.ilike(like)))
    out = []
    for m in db.scalars(stmt):
        scans = db.scalar(select(func.count()).select_from(Code).where(Code.scanned_by == m.id))
        out.append({"id": m.id, "phone": m.phone, "name": m.name, "city": m.city,
                    "specialization": m.specialization, "status": m.status, "scans": scans,
                    "balance": ledger.balance(db, m.id),
                    "level": ledger.level_info(ledger.earned_last_year(db, m.id))["level"],
                    "created_at": m.created_at})
    return out


class MasterPatch(BaseModel):
    status: Literal["active", "blocked"]
    reason: str = Field(min_length=3, max_length=255)


@router.patch("/masters/{mid}")
def patch_master(mid: int, body: MasterPatch, db: Session = Depends(get_db), staff: Staff = Depends(require("masters"))):
    m = db.get(Master, mid)
    if not m:
        raise HTTPException(404, "Мастер не найден")
    m.status = body.status
    audit.log(db, staff.id, "master.status", "master", m.id, status=body.status, reason=body.reason)
    db.commit()
    return {"id": m.id, "status": m.status}


class AdjustBody(BaseModel):
    points: int
    reason: str = Field(min_length=3, max_length=255)


@router.post("/masters/{mid}/adjust")
def adjust(mid: int, body: AdjustBody, db: Session = Depends(get_db), staff: Staff = Depends(require("adjust"))):
    """Ручная корректировка баллов — только администратор."""
    m = db.get(Master, mid)
    if not m:
        raise HTTPException(404, "Мастер не найден")
    if body.points < 0 and ledger.balance(db, m.id) + body.points < 0:
        raise HTTPException(400, "Баланс не может стать отрицательным")
    ledger.add_entry(db, m.id, "adjust", body.points, note=body.reason)
    audit.log(db, staff.id, "master.adjust", "master", m.id, points=body.points, reason=body.reason)
    db.commit()
    return {"balance": ledger.balance(db, m.id)}


# ---------- Фрод ----------

@router.get("/fraud")
def fraud(status: str = "open", db: Session = Depends(get_db), _: Staff = Depends(require("fraud"))):
    rows = db.execute(select(FraudFlag, Master.phone, Master.name).join(Master, isouter=True)
                      .where(FraudFlag.status == status).order_by(FraudFlag.id.desc()).limit(200))
    return [{"id": f.id, "kind": f.kind, "detail": f.detail, "code": f.code_value, "master_id": f.master_id,
             "master": name or phone, "status": f.status, "created_at": f.created_at} for f, phone, name in rows]


class ResolveBody(BaseModel):
    decision: Literal["released", "confirmed"]


@router.post("/fraud/{fid}/resolve")
def resolve(fid: int, body: ResolveBody, db: Session = Depends(get_db), staff: Staff = Depends(require("fraud"))):
    flag = db.get(FraudFlag, fid)
    if not flag:
        raise HTTPException(404, "Не найдено")
    try:
        rewards.resolve_flag(db, flag, body.decision, staff.id)
    except rewards.RewardError as e:
        raise HTTPException(400, str(e))
    audit.log(db, staff.id, "fraud.resolve", "fraud_flag", flag.id, decision=body.decision)
    db.commit()
    return {"id": flag.id, "status": flag.status}


# ---------- Награды и заявки ----------

class RewardBody(BaseModel):
    title: str = Field(max_length=160)
    description: Optional[str] = None
    kind: Literal["cash", "product", "trip"]
    cost_points: int = Field(gt=0)
    min_level: Optional[str] = None
    stock: Optional[int] = Field(default=None, ge=0)
    active: bool = True


@router.get("/rewards")
def admin_rewards(db: Session = Depends(get_db), _: Staff = Depends(current_staff)):
    return [{"id": r.id, "title": r.title, "kind": r.kind, "cost_points": r.cost_points, "min_level": r.min_level,
             "stock": r.stock, "active": r.active} for r in db.scalars(select(Reward).order_by(Reward.cost_points))]


@router.post("/rewards")
def create_reward(body: RewardBody, db: Session = Depends(get_db), staff: Staff = Depends(require("rewards"))):
    r = Reward(**body.model_dump())
    db.add(r)
    db.flush()
    audit.log(db, staff.id, "reward.create", "reward", r.id, title=r.title, cost=r.cost_points)
    db.commit()
    return {"id": r.id}


@router.get("/redemptions")
def redemptions(status: Optional[str] = "pending", db: Session = Depends(get_db),
                _: Staff = Depends(require("redemptions"))):
    stmt = select(Redemption).order_by(Redemption.id.desc()).limit(200)
    if status:
        stmt = stmt.where(Redemption.status == status)
    return [{"id": r.id, "master_id": r.master_id, "master": r.master.name or r.master.phone, "phone": r.master.phone,
             "reward": r.reward.title, "kind": r.reward.kind, "points": r.points, "status": r.status,
             "created_at": r.created_at} for r in db.scalars(stmt)]


class RedemptionStatus(BaseModel):
    status: Literal["approved", "done", "rejected"]
    comment: Optional[str] = None


@router.post("/redemptions/{rid}/status")
def set_redemption_status(rid: int, body: RedemptionStatus, db: Session = Depends(get_db),
                          staff: Staff = Depends(require("redemptions"))):
    red = db.get(Redemption, rid)
    if not red:
        raise HTTPException(404, "Заявка не найдена")
    try:
        rewards.process(db, red, body.status, staff.id, body.comment)
    except rewards.RewardError as e:
        raise HTTPException(400, str(e))
    audit.log(db, staff.id, "redemption.status", "redemption", red.id, status=body.status)
    db.commit()
    return {"id": red.id, "status": red.status}


# ---------- Дашборд ----------

@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _: Staff = Depends(require("view"))):
    status_counts = dict(db.execute(select(Code.status, func.count()).group_by(Code.status)).all())
    activated = status_counts.get("activated", 0) + status_counts.get("scanned", 0)
    scanned = status_counts.get("scanned", 0)
    masters_total = db.scalar(select(func.count()).select_from(Master))
    masters_active = db.scalar(select(func.count(func.distinct(Code.scanned_by))).where(Code.scanned_by.is_not(None)))
    liability = db.scalar(select(func.coalesce(func.sum(LedgerEntry.points), 0)).where(LedgerEntry.frozen.is_(False)))

    by_product = db.execute(select(Product.name, func.count(Code.id)).join(Product)
                            .where(Code.status == "scanned").group_by(Product.name)
                            .order_by(func.count(Code.id).desc())).all()
    by_dealer = db.execute(select(Dealer.name, Dealer.city, func.count(Code.id),
                                  func.sum(case((Code.status == "scanned", 1), else_=0)))
                           .join(Dealer, Code.dealer_id == Dealer.id)
                           .group_by(Dealer.id, Dealer.name, Dealer.city)).all()
    by_city = db.execute(select(Master.city, func.count(Code.id)).join(Master, Code.scanned_by == Master.id)
                         .group_by(Master.city).order_by(func.count(Code.id).desc())).all()
    open_fraud = db.scalar(select(func.count()).select_from(FraudFlag).where(FraudFlag.status == "open"))
    pending_red = db.scalar(select(func.count()).select_from(Redemption).where(Redemption.status == "pending"))
    return {
        "codes": {"loaded": sum(status_counts.values()), "activated": activated, "scanned": scanned,
                  "scan_rate_pct": round(scanned * 100 / activated, 1) if activated else 0},
        "masters": {"registered": masters_total, "active": masters_active},
        "points_liability": int(liability),
        "by_product": [{"product": n, "scanned": c} for n, c in by_product],
        "by_dealer": [{"dealer": n, "city": city, "shipped": shipped, "scanned": int(sc or 0),
                       "scan_rate_pct": round(int(sc or 0) * 100 / shipped, 1) if shipped else 0}
                      for n, city, shipped, sc in by_dealer],
        "by_city": [{"city": c or "не указан", "scanned": n} for c, n in by_city],
        "open_fraud_flags": open_fraud,
        "pending_redemptions": pending_red,
    }


@router.get("/audit")
def audit_log(limit: int = 100, db: Session = Depends(get_db), _: Staff = Depends(require("audit"))):
    rows = db.execute(select(AuditLog, Staff.email).join(Staff, isouter=True)
                      .order_by(AuditLog.id.desc()).limit(min(limit, 500)))
    return [{"id": a.id, "who": email, "action": a.action, "entity": a.entity, "entity_id": a.entity_id,
             "detail": a.detail, "at": a.created_at} for a, email in rows]
