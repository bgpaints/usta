"""Сгорание баллов и уровни."""
from datetime import timedelta

from app.db import SessionLocal, utcnow
from app.models import Master
from app.services import ledger


def test_expire_oldest_first(client):
    now = utcnow()
    with SessionLocal() as db:
        m = Master(phone="+77015550000")
        db.add(m)
        db.flush()
        old = now - timedelta(days=400)
        ledger.add_entry(db, m.id, "scan", 1000, now=old)          # сгорел
        ledger.add_entry(db, m.id, "redeem", -300, now=old + timedelta(days=10))  # потратил из старых
        ledger.add_entry(db, m.id, "scan", 500, now=now)            # свежие
        db.flush()
        assert ledger.expire_points(db, m, now) == 700              # 1000 − 300 потрачено
        assert ledger.expire_points(db, m, now) == 0                # повторно не сгорает
        assert ledger.balance(db, m.id) == 500


def test_levels():
    assert ledger.level_info(0)["level"] == "Старт"
    info = ledger.level_info(3000)
    assert info["level"] == "Бронза" and info["next_level"] == "Серебро" and info["points_to_next"] == 2000
    assert ledger.level_info(20000)["next_level"] is None
