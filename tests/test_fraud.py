"""Антифрод. В тестах лимиты занижены: всплеск > 5 сканов, сутки — 8, ручных ошибок — 3."""
from .conftest import generate_and_ship, master_headers, staff_headers


def test_code_not_activated(client):
    codes = generate_and_ship(client, count=1, ship=False)
    m = master_headers(client)
    r = client.post("/scan", json={"code": codes[0]}, headers=m)
    assert r.status_code == 400 and r.json()["detail"]["reason"] == "not_activated"
    flags = client.get("/admin/fraud", headers=staff_headers(client)).json()
    assert flags[0]["kind"] == "not_activated"


def test_foreign_code(client):
    codes = generate_and_ship(client, count=1)
    a = master_headers(client, "+77010000001", "А")
    b = master_headers(client, "+77010000002", "Б")
    assert client.post("/scan", json={"code": codes[0]}, headers=a).status_code == 200
    assert client.post("/scan", json={"code": codes[0]}, headers=b).status_code == 409
    flags = client.get("/admin/fraud", headers=staff_headers(client)).json()
    assert any(f["kind"] == "foreign_code" for f in flags)


def test_burst_freezes_then_release(client):
    codes = generate_and_ship(client, sku="INT9", count=7)  # 90 баллов за банку
    m = master_headers(client)
    for c in codes:
        r = client.post("/scan", json={"code": c}, headers=m)
        assert r.status_code == 200, r.text
    me = client.get("/me", headers=m).json()
    # 5 обычных сканов + бонус видны, 6-й и 7-й заморожены
    assert me["balance"] == 5 * 90 + 100
    assert me["on_review"] == 2 * 90

    admin = staff_headers(client)
    flag = next(f for f in client.get("/admin/fraud", headers=admin).json() if f["kind"] == "burst")
    # пока проверка не закрыта, обмен запрещён
    rid = client.get("/rewards", headers=m).json()[0]["id"]
    assert client.post(f"/rewards/{rid}/redeem", headers=m).status_code == 400

    r = client.post(f"/admin/fraud/{flag['id']}/resolve", json={"decision": "released"}, headers=admin)
    assert r.status_code == 200
    assert client.get("/me", headers=m).json()["balance"] == 7 * 90 + 100


def test_burst_confirmed_keeps_points_frozen(client):
    codes = generate_and_ship(client, sku="INT9", count=7)
    m = master_headers(client)
    for c in codes:
        client.post("/scan", json={"code": c}, headers=m)
    admin = staff_headers(client)
    flag = next(f for f in client.get("/admin/fraud", headers=admin).json() if f["kind"] == "burst")
    client.post(f"/admin/fraud/{flag['id']}/resolve", json={"decision": "confirmed"}, headers=admin)
    assert client.get("/me", headers=m).json()["balance"] == 5 * 90 + 100


def test_daily_limit(client):
    codes = generate_and_ship(client, sku="INT9", count=9)
    m = master_headers(client)
    results = [client.post("/scan", json={"code": c}, headers=m).status_code for c in codes]
    assert results[:8] == [200] * 8 and results[8] == 400


def test_manual_bruteforce_locks(client):
    generate_and_ship(client, count=1)
    m = master_headers(client)
    for i in range(3):
        r = client.post("/scan", json={"code": f"9999999999999{i}", "manual": True}, headers=m)
        assert r.json()["detail"]["reason"] == "not_found"
    r = client.post("/scan", json={"code": "99999999999998", "manual": True}, headers=m)
    assert r.json()["detail"]["reason"] == "manual_locked"


def test_blocked_master(client):
    codes = generate_and_ship(client, count=1)
    m = master_headers(client)
    admin = staff_headers(client)
    mid = client.get("/admin/masters", headers=admin).json()[0]["id"]
    client.patch(f"/admin/masters/{mid}", json={"status": "blocked", "reason": "проверка"}, headers=admin)
    assert client.post("/scan", json={"code": codes[0]}, headers=m).status_code == 403
