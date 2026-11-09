from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Master, Staff
from ..security import read_token

# Что может делать каждая роль сотрудника
PERMISSIONS = {
    "admin": {"*"},
    "marketing": {"view", "codes", "products", "rewards", "masters", "fraud"},
    "warehouse": {"view_shipments", "ship"},
    "finance": {"view", "redemptions"},
}


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Нужна авторизация")
    return authorization.split(" ", 1)[1]


def current_master(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> Master:
    data = read_token(_bearer(authorization))
    if not data or data.get("typ") != "master":
        raise HTTPException(401, "Сессия истекла, войдите снова")
    master = db.get(Master, int(data["sub"]))
    if master is None:
        raise HTTPException(401, "Аккаунт не найден")
    if master.status != "active":
        raise HTTPException(403, "Аккаунт заблокирован")
    return master


def current_staff(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> Staff:
    data = read_token(_bearer(authorization))
    if not data or data.get("typ") != "staff":
        raise HTTPException(401, "Сессия истекла, войдите снова")
    staff = db.get(Staff, int(data["sub"]))
    if staff is None or not staff.active:
        raise HTTPException(401, "Доступ закрыт")
    return staff


def require(permission: str):
    def checker(staff: Staff = Depends(current_staff)) -> Staff:
        allowed = PERMISSIONS.get(staff.role, set())
        if "*" not in allowed and permission not in allowed:
            raise HTTPException(403, "Недостаточно прав для этого действия")
        return staff
    return checker
