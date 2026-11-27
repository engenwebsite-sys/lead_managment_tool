"""Append-only change evidence; client supplied history is never accepted."""
import uuid
from datetime import datetime, timezone
from app.services.crm_access import actor


def value(item):
    if isinstance(item, datetime):
        return item.replace(tzinfo=timezone.utc).isoformat() if item.tzinfo is None else item.astimezone(timezone.utc).isoformat()
    return item


def snapshot(record, fields):
    return {field: value(getattr(record, field)) for field in fields}


def entry(db, message, before=None, after=None, at=None):
    user = actor(db)
    changes = {key: {"before": before.get(key), "after": item} for key, item in (after or {}).items()
               if (before or {}).get(key) != item}
    return {"id": str(uuid.uuid4()), "at": (at or datetime.now(timezone.utc)).isoformat(),
            "message": message, "actor": user.name if user else "System", "changes": changes}
