"""Коды в банках: загрузка, генерация, активация отгрузкой и скан мастером с антифродом."""
import csv
import io
import secrets
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import utcnow
from ..models import Code, CodeBatch, Dealer, FraudFlag, LedgerEntry, Master, Product, ScanAttempt, Shipment
from . import ledger


class CodeError(Exception):
    pass


# ---------- Загрузка и генерация ----------

@dataclass
class ImportReport:
    batch_id: Optional[int] = None
    added: int = 0
    duplicates: int = 0
    errors: list = field(default_factory=list)  # [(строка, причина)]


def _valid_code(value: str) -> bool:
    return value.isdigit() and len(value) == settings.code_length


def import_codes_csv(db: Session, content: bytes, batch_name: str, source: str, staff_id: Optional[int]) -> ImportReport:
    """Файл кодов от Asian Paints или наш: колонки code,sku (заголовок обязателен)."""
    report = ImportReport()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=";" if text.count(";") > text.count(",") else ",")
    headers = {h.strip().lower() for h in (reader.fieldnames or [])}
    if not {"code", "sku"} <= headers:
        raise CodeError("В файле нужны колонки code и sku")

    products = {p.sku: p.id for p in db.scalars(select(Product))}
    rows = []
    seen = set()
    for i, raw in enumerate(reader, start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        value, sku = row.get("code", ""), row.get("sku", "")
        if not _valid_code(value):
            report.errors.append((i, f"код должен быть из {settings.code_length} цифр"))
            continue
        if sku not in products:
            report.errors.append((i, f"неизвестный SKU {sku}"))
            continue
        if value in seen:
            report.duplicates += 1
            continue
        seen.add(value)
        rows.append((value, products[sku]))

    existing = set()
    values = [v for v, _ in rows]
    for chunk_start in range(0, len(values), 500):
        chunk = values[chunk_start:chunk_start + 500]
        existing.update(db.scalars(select(Code.value).where(Code.value.in_(chunk))))

    batch = CodeBatch(name=batch_name, source=source, created_by=staff_id)
    db.add(batch)
    db.flush()
    report.batch_id = batch.id
    for value, product_id in rows:
        if value in existing:
            report.duplicates += 1
            continue
        db.add(Code(value=value, batch_id=batch.id, product_id=product_id))
        report.added += 1
    return report


def generate_codes(db: Session, product: Product, count: int, batch_name: str, staff_id: Optional[int]) -> CodeBatch:
    """Свои коды BGP: случайные (не по порядку), уникальные, без ведущего нуля."""
    if not 1 <= count <= 100_000:
        raise CodeError("Количество от 1 до 100 000")
    batch = CodeBatch(name=batch_name, source="bgp", created_by=staff_id)
    db.add(batch)
    db.flush()
    made = set()
    low = 10 ** (settings.code_length - 1)
    while len(made) < count:
        need = count - len(made)
        candidates = {str(low + secrets.randbelow(9 * low)) for _ in range(need)} - made
        taken = set(db.scalars(select(Code.value).where(Code.value.in_(list(candidates)))))
        for value in candidates - taken:
            db.add(Code(value=value, batch_id=batch.id, product_id=product.id))
            made.add(value)
    return batch


# ---------- Отгрузка: коды оживают ----------

@dataclass
class ShipReport:
    shipment_id: int
    activated: int = 0
    not_found: list = field(default_factory=list)
    already_used: list = field(default_factory=list)


def ship_codes(db: Session, dealer: Dealer, values: Iterable[str], staff_id: Optional[int], note: Optional[str] = None) -> ShipReport:
    shipment = Shipment(dealer_id=dealer.id, note=note, created_by=staff_id)
    db.add(shipment)
    db.flush()
    report = ShipReport(shipment_id=shipment.id)
    now = utcnow()
    values = list(dict.fromkeys(v.strip() for v in values if v and v.strip()))
    by_value = {}
    for i in range(0, len(values), 500):
        for c in db.scalars(select(Code).where(Code.value.in_(values[i:i + 500]))):
            by_value[c.value] = c
    for v in values:
        code = by_value.get(v)
        if code is None:
            report.not_found.append(v)
        elif code.status != "loaded":
            report.already_used.append(v)
        else:
            code.status, code.dealer_id, code.shipment_id, code.activated_at = "activated", dealer.id, shipment.id, now
            report.activated += 1
    return report


# ---------- Скан мастером ----------

@dataclass
class ScanResult:
    ok: bool
    reason: str               # ok / not_found / not_activated / already_scanned / blocked / daily_limit / manual_locked / invalid
    message: str
    points: int = 0
    frozen: bool = False
    product: Optional[str] = None
    volume: Optional[str] = None
    calc: Optional[str] = None


MESSAGES = {
    "invalid": "Неверный формат кода",
    "not_found": "Код не найден. Проверьте цифры",
    "not_activated": "Код ещё не активирован. Обратитесь к продавцу",
    "already_scanned": "Этот код уже использован",
    "blocked": "Аккаунт заблокирован. Свяжитесь с поддержкой",
    "daily_limit": "Достигнут дневной лимит сканов. Попробуйте завтра",
    "manual_locked": "Слишком много неверных вводов. Ручной ввод доступен через 24 часа",
}


def points_for(product: Product) -> tuple[int, str]:
    pts = round(product.volume * product.points_per_unit * product.multiplier)
    calc = f"{product.volume:g} {product.unit} × {product.points_per_unit}"
    if product.multiplier != 1:
        calc += f" × {product.multiplier:g} акция"
    return pts, calc


def _flag(db, master_id, kind, detail, code_value=None):
    db.add(FraudFlag(master_id=master_id, kind=kind, detail=detail, code_value=code_value))


def scan(db: Session, master: Master, raw_value: str, *, manual: bool = False,
         lat: Optional[float] = None, lng: Optional[float] = None) -> ScanResult:
    now = utcnow()
    value = "".join(ch for ch in (raw_value or "") if ch.isdigit()) if manual else (raw_value or "").strip()
    # QR может содержать ссылку вида https://.../c/12345678901234 — берём последние цифры
    if not manual and not _valid_code(value):
        tail = "".join(ch for ch in value.split("/")[-1].split("=")[-1] if ch.isdigit())
        value = tail

    def fail(reason: str) -> ScanResult:
        db.add(ScanAttempt(master_id=master.id, code_value=value[:64], manual=manual, success=False,
                           reason=reason, lat=lat, lng=lng, created_at=now))
        return ScanResult(False, reason, MESSAGES[reason])

    if master.status != "active":
        return fail("blocked")
    if manual and master.manual_blocked_until and master.manual_blocked_until > now:
        return fail("manual_locked")
    if not _valid_code(value):
        return _manual_fail(db, master, fail("invalid"), manual, now)

    # Блокируем строку кода, чтобы два одновременных скана не прошли оба (PostgreSQL)
    code = db.scalars(select(Code).where(Code.value == value).with_for_update()).first()
    if code is None:
        return _manual_fail(db, master, fail("not_found"), manual, now)
    if code.status == "scanned":
        if code.scanned_by != master.id:
            _flag(db, master.id, "foreign_code", "Попытка скана кода, уже использованного другим мастером", value)
        return fail("already_scanned")
    if code.status != "activated":
        _flag(db, master.id, "not_activated", "Скан кода, который не прошёл отгрузку со склада", value)
        return fail("not_activated")

    day_ago = now - timedelta(days=1)
    today_scans = db.scalar(select(func.count()).select_from(ScanAttempt).where(
        ScanAttempt.master_id == master.id, ScanAttempt.success.is_(True), ScanAttempt.created_at >= day_ago))
    if today_scans >= settings.max_scans_per_day:
        _flag(db, master.id, "daily_limit", f"Больше {settings.max_scans_per_day} сканов за сутки", value)
        return fail("daily_limit")

    window = now - timedelta(minutes=settings.burst_window_minutes)
    recent = db.scalar(select(func.count()).select_from(ScanAttempt).where(
        ScanAttempt.master_id == master.id, ScanAttempt.success.is_(True), ScanAttempt.created_at >= window))
    open_burst = db.scalar(select(func.count()).select_from(FraudFlag).where(
        FraudFlag.master_id == master.id, FraudFlag.kind == "burst", FraudFlag.status == "open"))
    burst = open_burst > 0 or recent + 1 > settings.burst_max_scans
    if burst and not open_burst:
        _flag(db, master.id, "burst",
              f"Больше {settings.burst_max_scans} сканов за {settings.burst_window_minutes} мин — начисления заморожены")

    product = code.product
    pts, calc = points_for(product)
    code.status, code.scanned_at, code.scanned_by, code.scan_lat, code.scan_lng = "scanned", now, master.id, lat, lng

    first_scan = not db.scalar(select(func.count()).select_from(LedgerEntry).where(
        LedgerEntry.master_id == master.id, LedgerEntry.kind == "scan"))
    db.flush()
    ledger.add_entry(db, master.id, "scan", pts, code_id=code.id, frozen=burst, now=now,
                     note=f"{product.name}, {product.volume:g} {product.unit}")
    if first_scan and settings.welcome_bonus:
        ledger.add_entry(db, master.id, "bonus", settings.welcome_bonus, now=now, note="Приветственные баллы")
    db.add(ScanAttempt(master_id=master.id, code_value=value, manual=manual, success=True, reason="ok",
                       lat=lat, lng=lng, created_at=now))
    msg = "Баллы начислены" if not burst else "Баллы начислены и проходят проверку"
    return ScanResult(True, "ok", msg, points=pts, frozen=burst, product=product.name,
                      volume=f"{product.volume:g} {product.unit}", calc=calc)


def _manual_fail(db: Session, master: Master, result: ScanResult, manual: bool, now) -> ScanResult:
    """Ограничиваем подбор кодов вручную."""
    if not manual:
        return result
    db.flush()
    fails = db.scalar(select(func.count()).select_from(ScanAttempt).where(
        ScanAttempt.master_id == master.id, ScanAttempt.manual.is_(True), ScanAttempt.success.is_(False),
        ScanAttempt.reason.in_(("invalid", "not_found")), ScanAttempt.created_at >= now - timedelta(days=1)))
    if fails >= settings.manual_fail_limit:
        master.manual_blocked_until = now + timedelta(days=1)
        _flag(db, master.id, "manual_bruteforce", f"{fails} неверных ручных вводов за сутки")
    return result
