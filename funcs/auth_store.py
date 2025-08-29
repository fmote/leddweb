from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Optional


AUTH_STATES = "oauth_states"
USERS = "users"
SESSIONS = "sessions"


def _states(db):
    return db[AUTH_STATES]


def _users(db):
    return db[USERS]


def _sessions(db):
    return db[SESSIONS]


def create_auth_indexes(db) -> bool:
    try:
        # OAuth state: unique and TTL (10 minutes)
        s = _states(db)
        s.create_index([("state", 1)], unique=True, name="uniq_state")
        s.create_index([("created_at", 1)], expireAfterSeconds=600, name="ttl_state_10m")

        # Users: discord_id unique
        u = _users(db)
        u.create_index([("discord_id", 1)], unique=True, name="uniq_discord_id")
        u.create_index([("updated_at", -1)], name="idx_user_updated_desc")

        # Sessions: session_id unique + TTL (default 30 days)
        sess = _sessions(db)
        sess.create_index([("session_id", 1)], unique=True, name="uniq_session_id")
        ttl_days = int(os.getenv("AUTH_SESSION_TTL_DAYS", "30"))
        sess.create_index([("created_at", 1)], expireAfterSeconds=ttl_days * 24 * 3600, name="ttl_session")
        return True
    except Exception as e:
        print(f"Error creating auth indexes: {e}")
        return False


def save_oauth_state(db, state: str, continue_to: Optional[str]) -> Dict[str, Any]:
    doc = {
        "state": state,
        "continue": continue_to,
        "created_at": datetime.now(timezone.utc),
    }
    _states(db).insert_one(doc)
    return doc


def consume_oauth_state(db, state: str) -> Optional[Dict[str, Any]]:
    return _states(db).find_one_and_delete({"state": state})


def upsert_discord_user(db, discord_user: Dict[str, Any], token_info: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    discord_id = str(discord_user.get("id"))
    profile = {
        "discord_id": discord_id,
        "username": discord_user.get("username"),
        "global_name": discord_user.get("global_name"),
        "avatar": discord_user.get("avatar"),
        "discriminator": discord_user.get("discriminator"),
        "updated_at": now,
        "token": token_info,
    }
    _users(db).update_one({"discord_id": discord_id}, {"$set": profile, "$setOnInsert": {"created_at": now}}, upsert=True)
    return _users(db).find_one({"discord_id": discord_id})  # type: ignore[return-value]


def new_session(db, discord_id: str) -> str:
    session_id = secrets.token_urlsafe(32)
    doc = {
        "session_id": session_id,
        "discord_id": str(discord_id),
        "created_at": datetime.now(timezone.utc),
    }
    _sessions(db).insert_one(doc)
    return session_id


def get_user_by_session(db, session_id: str) -> Optional[Dict[str, Any]]:
    sess = _sessions(db).find_one({"session_id": session_id})
    if not sess:
        return None
    return _users(db).find_one({"discord_id": sess.get("discord_id")})


def delete_session(db, session_id: str) -> bool:
    res = _sessions(db).delete_one({"session_id": session_id})
    return res.deleted_count > 0
