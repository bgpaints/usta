"""Служебные команды.
  python -m app.cli create-admin email@bgp.kz "Имя" пароль [роль]
  python -m app.cli seed-demo          — демо-продукты, дилеры, награды
  python -m app.cli expire-points      — сгорание баллов (запускать раз в сутки)
"""
import sys

from sqlalchemy import select

from .db import Base, SessionLocal, engine
from .models import Dealer, Master, Product, Reward, Staff
from .security import hash_password
from .services import ledger


def create_admin(email: str, name: str, password: str, role: str = "admin") -> None:
    if len(password) < 10:
        sys.exit("Пароль должен быть не короче 10 символов")
    with SessionLocal() as db:
        if db.scalar(select(Staff.id).where(Staff.email == email.lower())):
            sys.exit("Такой сотрудник уже есть")
        db.add(Staff(email=email.lower(), name=name, role=role, password_hash=hash_password(password)))
        db.commit()
    print(f"Создан сотрудник {email} ({role})")


DEMO_PRODUCTS = [
    ("SC-VITALIA-NEO-18", "Vitalia NEO", "waterproofing", 18, "л", 10, 2.0),
    ("SC-DAMP-PROOF-20", "Damp Proof", "waterproofing", 20, "кг", 10, 2.0),
    ("SC-REPAIR-POLYMER-20", "Repair Polymer", "waterproofing", 20, "кг", 10, 2.0),
    ("SC-DAMP-BLOCK-2K-20", "Damp Block 2K", "waterproofing", 20, "кг", 10, 2.0),
]
DEMO_REWARDS = [
    ("Спецодежда Bekmetov", "product", 2000, None),
    ("Набор валиков и кистей", "product", 3000, None),
    ("Вывод на карту 5 000 ₸", "cash", 5000, None),
    ("Поездка для лучших мастеров", "trip", 15000, "Золото"),
]


def seed_demo() -> None:
    with SessionLocal() as db:
        for sku, name, cat, vol, unit, ppu, mult in DEMO_PRODUCTS:
            if not db.scalar(select(Product.id).where(Product.sku == sku)):
                db.add(Product(sku=sku, name=name, category=cat, volume=vol, unit=unit,
                               points_per_unit=ppu, multiplier=mult))
        if not db.scalar(select(Dealer.id)):
            db.add(Dealer(name="Демо-дилер Алматы", city="Алматы"))
        if not db.scalar(select(Reward.id)):
            for title, kind, cost, lvl in DEMO_REWARDS:
                db.add(Reward(title=title, kind=kind, cost_points=cost, min_level=lvl))
        db.commit()
    print("Демо-данные добавлены (SKU и баллы — примерные, заменить реальными)")


def expire_points() -> None:
    total = 0
    with SessionLocal() as db:
        for m in db.scalars(select(Master)):
            total += ledger.expire_points(db, m)
        db.commit()
    print(f"Сгорело баллов: {total}")


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    cmd, args = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ("", [])
    if cmd == "create-admin" and len(args) >= 3:
        create_admin(*args[:4])
    elif cmd == "seed-demo":
        seed_demo()
    elif cmd == "expire-points":
        expire_points()
    else:
        print(__doc__)
