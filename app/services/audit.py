from typing import Optional

from sqlalchemy.orm import Session

from ..models import AuditLog


def log(db: Session, staff_id: Optional[int], action: str, entity: Optional[str] = None,
        entity_id: Optional[int] = None, **detail) -> None:
    db.add(AuditLog(staff_id=staff_id, action=action, entity=entity, entity_id=entity_id,
                    detail=detail or None))
