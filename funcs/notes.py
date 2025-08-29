from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    from bson import ObjectId  # type: ignore
except Exception:  # pragma: no cover - fallback if bson is unavailable
    class ObjectId:  # pyright: ignore[reportGeneralTypeIssues]
        pass


COLLECTION_NAME = "user_notes"


def _coll(db):
    return db[COLLECTION_NAME]


def create_note_indexes(db) -> bool:
    try:
        c = _coll(db)
        c.create_index([("user_id", 1)], unique=True, name="uniq_user_id")
        c.create_index([("updated_at", -1)], name="idx_updated_at_desc")
        return True
    except Exception as e:
        print(f"Error creating note indexes: {e}")
        return False


def set_user_note(db, user_id: int, content: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    c = _coll(db)
    if not isinstance(content, str):
        content = str(content)
    note_doc = {
        "user_id": int(user_id),
        "content": content,
        "updated_at": now,
    }
    update = {"$set": note_doc, "$setOnInsert": {"created_at": now}}
    c.update_one({"user_id": int(user_id)}, update, upsert=True)
    doc = c.find_one({"user_id": int(user_id)})
    return doc  # type: ignore[return-value]


def get_user_note(db, user_id: int) -> Optional[Dict[str, Any]]:
    return _coll(db).find_one({"user_id": int(user_id)})


def delete_user_note(db, user_id: int) -> bool:
    res = _coll(db).delete_one({"user_id": int(user_id)})
    return res.deleted_count > 0


def to_api(doc: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(doc)
    _id = out.get("_id")
    if isinstance(_id, ObjectId):
        out["_id"] = str(_id)
    for k in ("created_at", "updated_at"):
        v = out.get(k)
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out
