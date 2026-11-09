"""Весь путь банки: коды -> отгрузка -> скан -> баллы -> обмен -> выплата."""
from datetime import timedelta

from app.db import SessionLocal
from app.models import LedgerEntry
from app.security import normalize_phone

from .conftest import generate_and_ship, master_headers, staff_headers


def _release_hold():
    """Сдвигаем удержание баллов в прошлое (как будто прошло 3 дня)."""
    with SessionLocal() as db:
        for e in db.query(LedgerEntry).filter(LedgerEntry.available_at.is_not(None)):
            e.available_at = e.available_at - timedelta(days=10)
        db.commit()


def test_phones():
    assert normalize_phone("8 701 234 56 78") == "+77012345678"
    assert normalize_phone("+7 (701) 234-56-78") == "+77012345678"
    assert normalize_phone("+998 90 123 45 67") == "+998901234567"
    assert normalize_phone("12345") is None


def test_wrong_otp(client):
    client.post("/auth/otp/request", json={"phone": "+77010000001"})
    r = client.post("/auth/otp/verify", json={"phone": "+77010000001", "code": "abcd"})
    assert r.status_code == 400


def test_full_path(client):
    codes = generate_and_ship(client, count=3)
    assert all(len(c) == 14 and c.isdigit() for c in codes)
    m = master_headers(client)

    r = client.post("/scan", json={"code": codes[0]}, headers=m)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["points"] == 360            # 18 л × 10 × 2 акция
    assert body["balance"] == 460           # + 100 приветственных

    # QR со ссылкой тоже работает
    r = client.post("/scan", json={"code": f"https://usta.kz/c/{codes[1]}"}, headers=m)
    assert r.status_code == 200
    # ручной ввод с пробелами
    r = client.post("/scan", json={"code": " ".join([codes[2][:7], codes[2][7:]]), "manual": True}, headers=m)
    assert r.status_code == 200

    me = client.get("/me", headers=m).json()
    assert me["balance"] == 100 + 360 * 3
    assert me["available"] == 0             # баллы на удержании 3 дня
    assert me["level"] == "Бронза"

    # повторный скан того же кода
    r = client.post("/scan", json={"code": codes[0]}, headers=m)
    assert r.status_code == 409

    # обмен до окончания удержания — нельзя
    rewards = client.get("/rewards", headers=m).json()
    valiki = next(x for x in rewards if x["title"] == "Валики")
    assert client.post(f"/rewards/{valiki['id']}/redeem", headers=m).status_code == 400

    _release_hold()
    r = client.post(f"/rewards/{valiki['id']}/redeem", headers=m)
    assert r.status_code == 200, r.text
    assert r.json()["balance"] == 1180 - 300

    # поездка — только с уровня Золото
    trip = next(x for x in rewards if x["title"] == "Поездка")
    assert client.post(f"/rewards/{trip['id']}/redeem", headers=m).status_code == 400

    # финансы отклоняют заявку — баллы возвращаются
    fin = staff_headers(client, "fin@bgp.kz", "fin-pass-1234")
    reds = client.get("/admin/redemptions", headers=fin).json()
    assert len(reds) == 1
    r = client.post(f"/admin/redemptions/{reds[0]['id']}/status", json={"status": "rejected"}, headers=fin)
    assert r.status_code == 200
    assert client.get("/me", headers=m).json()["balance"] == 1180

    # дашборд
    dash = client.get("/admin/dashboard", headers=staff_headers(client)).json()
    assert dash["codes"]["scanned"] == 3 and dash["codes"]["scan_rate_pct"] == 100.0
    assert dash["by_dealer"][0]["scanned"] == 3
    assert dash["masters"]["active"] == 1


def test_import_csv(client):
    admin = staff_headers(client)
    content = "code,sku\n12345678901234,VN18\n12345678901234,VN18\n123,VN18\n22345678901234,NOPE\n32345678901234,INT9\n"
    r = client.post("/admin/batches/import", data={"name": "AP октябрь", "source": "asian_paints"},
                    files={"file": ("codes.csv", content, "text/csv")}, headers=admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["added"] == 2 and body["duplicates"] == 1 and body["errors_total"] == 2


def test_roles(client):
    sklad = staff_headers(client, "sklad@bgp.kz", "sklad-pass-123")
    assert client.get("/admin/masters", headers=sklad).status_code == 403
    assert client.post("/admin/batches/generate", json={"sku": "VN18", "count": 1, "name": "x"},
                       headers=sklad).status_code == 403
    fin = staff_headers(client, "fin@bgp.kz", "fin-pass-1234")
    assert client.post("/admin/masters/1/adjust", json={"points": 1000, "reason": "test"},
                       headers=fin).status_code == 403
    assert client.get("/admin/audit", headers=staff_headers(client)).status_code == 200
    assert client.get("/me").status_code == 401
