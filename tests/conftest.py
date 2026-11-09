import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["DEBUG"] = "1"
os.environ["JWT_SECRET"] = "test-secret-at-least-32-bytes-long-xx"
os.environ["BURST_MAX_SCANS"] = "5"
os.environ["MAX_SCANS_PER_DAY"] = "8"
os.environ["MANUAL_FAIL_LIMIT"] = "3"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Dealer, Product, Reward, Staff  # noqa: E402
from app.security import hash_password  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.add_all([
            Staff(email="admin@bgp.kz", name="Админ", role="admin", password_hash=hash_password("admin-pass-123")),
            Staff(email="sklad@bgp.kz", name="Склад", role="warehouse", password_hash=hash_password("sklad-pass-123")),
            Staff(email="fin@bgp.kz", name="Финансы", role="finance", password_hash=hash_password("fin-pass-1234")),
            Product(sku="VN18", name="Vitalia NEO", category="waterproofing", volume=18, unit="л",
                    points_per_unit=10, multiplier=2),
            Product(sku="INT9", name="Интерьерная", category="interior", volume=9, unit="л", points_per_unit=10),
            Dealer(name="Дилер Алматы", city="Алматы"),
            Reward(title="Валики", kind="product", cost_points=300),
            Reward(title="Поездка", kind="trip", cost_points=500, min_level="Золото"),
        ])
        db.commit()
    with TestClient(create_app(create_tables=False)) as c:
        yield c


def staff_headers(client, email="admin@bgp.kz", password="admin-pass-123"):
    r = client.post("/admin/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def master_headers(client, phone="+7 701 234 56 78", name="Ерлан"):
    r = client.post("/auth/otp/request", json={"phone": phone})
    assert r.status_code == 200, r.text
    code = r.json()["debug_code"]
    r = client.post("/auth/otp/verify", json={"phone": phone, "code": code})
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    client.patch("/me", json={"name": name, "city": "Алматы", "specialization": "waterproofing"}, headers=h)
    return h


def generate_and_ship(client, sku="VN18", count=5, ship=True):
    admin = staff_headers(client)
    r = client.post("/admin/batches/generate", json={"sku": sku, "count": count, "name": "test"}, headers=admin)
    assert r.status_code == 200, r.text
    bid = r.json()["batch_id"]
    csv_text = client.get(f"/admin/batches/{bid}/export.csv", headers=admin).text
    values = [line.split(",")[0] for line in csv_text.strip().splitlines()[1:]]
    if ship:
        sklad = staff_headers(client, "sklad@bgp.kz", "sklad-pass-123")
        r = client.post("/admin/shipments", json={"dealer_id": 1, "codes": values}, headers=sklad)
        assert r.status_code == 200 and r.json()["activated"] == count, r.text
    return values
