from typing import Any

from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.db.models import Setting


def get_setting(db: Session, key: str) -> Any | None:
    row = db.query(Setting).filter_by(key=key).first()
    if row:
        return row.value_json
    return None


def get_all_settings(db: Session) -> dict[str, Any]:
    rows = db.query(Setting).all()
    return {row.key: row.value_json for row in rows}


def set_setting(db: Session, key: str, value: Any) -> Setting:
    row = db.query(Setting).filter_by(key=key).first()
    if row:
        row.value_json = value
        row.updated_at = utc_now()
    else:
        row = Setting(key=key, value_json=value)
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_setting(db: Session, key: str) -> bool:
    row = db.query(Setting).filter_by(key=key).first()
    if row:
        db.delete(row)
        db.commit()
        return True
    return False
