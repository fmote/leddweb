from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Optional, List
from urllib.parse import urlparse
from datetime import datetime, timezone

from sanic import Sanic
from sanic.response import json, redirect, html
from sanic.exceptions import SanicException
from sanic.log import logger
from dotenv import load_dotenv

from funcs.connectDB import connect_to_mongodb
from funcs.auth_store import (
    create_auth_indexes,
    save_oauth_state,
    consume_oauth_state,
    upsert_discord_user,
    new_session,
    get_user_by_session,
    delete_session,
)
from funcs.discord_oauth import build_authorize_url, exchange_code_for_token, fetch_discord_user


load_dotenv()

app = Sanic("AuthLedd")


@app.listener("before_server_start")
async def setup_db(app: Sanic, _loop):
    client, db = connect_to_mongodb()
    if db is not None:
        create_auth_indexes(db)
        app.ctx.db = db
        app.ctx.client = client
        app.ctx.db_ready = True
    else:
        app.ctx.db_ready = False


def _require_db():
    db = getattr(app.ctx, "db", None)
    if db is None:
        raise SanicException("Database not available", status_code=503)
    return db


def _cookie_settings():
    # Use a parent domain so auth.ledd.live and ledd.live share the cookie
    domain = os.getenv("AUTH_COOKIE_DOMAIN", ".ledd.live")
    secure = os.getenv("AUTH_COOKIE_SECURE", "true").lower() == "true"
    samesite = os.getenv("AUTH_COOKIE_SAMESITE", "Lax")
    return {
        "domain": domain,
        "secure": secure,
        "httponly": True,
        "samesite": samesite,
        "path": "/",
    }


def _get_redirect_uri(request) -> str:
    # Prefer explicit env var, fallback to infer from request
    env_redirect = os.getenv("DISCORD_REDIRECT_URI")
    if env_redirect:
        return env_redirect
    scheme = "https" if request.headers.get("x-forwarded-proto", request.scheme) == "https" else "http"
    host = request.headers.get("x-forwarded-host", request.host)
    return f"{scheme}://{host}/discord/callback"


def _allowed_return_hosts() -> List[str]:
    raw = os.getenv("AUTH_ALLOWED_RETURN_HOSTS", "ledd.live")
    return [h.strip().lower() for h in raw.split(",") if h.strip()]


def _is_allowed_redirect_url(url: str) -> bool:
    try:
        p = urlparse(url)
        if not p.scheme or not p.netloc:
            return False
        host = p.netloc.split(":")[0].lower()
        for allowed in _allowed_return_hosts():
            if host == allowed or host.endswith("." + allowed):
                return True
        return False
    except Exception:
        return False


def _pick_continue_url(request) -> str:
    # Priority: explicit ?continue= -> X-Continue header -> Referer -> default
    provided = request.args.get("continue") or request.headers.get("x-continue") or request.headers.get("referer")
    if not provided:
        return f"https://{_allowed_return_hosts()[0]}/me"

    # Allow relative path by mapping to apex host
    if provided.startswith("/") and not provided.startswith("//"):
        return f"https://{_allowed_return_hosts()[0]}{provided}"

    # Only allow absolute HTTP(S) URLs within allowed hosts
    if _is_allowed_redirect_url(provided):
        return provided

    return f"https://{_allowed_return_hosts()[0]}/me"


@app.get("/ping")
async def ping(_request):
    return json({"status": "ok"})



@app.get("/")
async def index(request):
    return html("<h1>Welcome to the AuthLedd API</h1>")


@app.get("/discord/login")
async def discord_login(request):
    db = _require_db()

    client_id = os.getenv("DISCORD_CLIENT_ID")
    client_secret = os.getenv("DISCORD_CLIENT_SECRET")
    if not client_id or not client_secret:
        return json({"error": "DISCORD_CLIENT_ID/SECRET not configured"}, status=500)

    # Determine where to send the user after successful login
    continue_to = _pick_continue_url(request)

    # CSRF state
    state = secrets.token_urlsafe(24)
    save_oauth_state(db, state, continue_to)

    redirect_uri = _get_redirect_uri(request)
    scope = os.getenv("DISCORD_SCOPE", "identify")
    url = build_authorize_url(client_id=client_id, state=state, redirect_uri=redirect_uri, scope=scope)
    return redirect(url)


@app.get("/discord/callback")
async def discord_callback(request):
    db = _require_db()

    client_id = os.getenv("DISCORD_CLIENT_ID")
    client_secret = os.getenv("DISCORD_CLIENT_SECRET")
    if not client_id or not client_secret:
        return json({"error": "DISCORD_CLIENT_ID/SECRET not configured"}, status=500)

    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")

    if error:
        return html(f"<h3>Discord error: {error}</h3>")
    if not code or not state:
        return json({"error": "Missing code or state"}, status=400)

    state_doc = consume_oauth_state(db, state)
    if not state_doc:
        return json({"error": "Invalid or expired state"}, status=400)

    redirect_uri = _get_redirect_uri(request)

    try:
        token = await exchange_code_for_token(
            code=code,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
        )
        userinfo = await fetch_discord_user(token["access_token"])  # type: ignore[index]

        user_doc = upsert_discord_user(
            db,
            discord_user=userinfo,
            token_info={
                "access_token": token.get("access_token"),
                "refresh_token": token.get("refresh_token"),
                "expires_in": token.get("expires_in"),
                "scope": token.get("scope"),
                "token_type": token.get("token_type"),
            },
        )

        session_id = new_session(db, user_doc["discord_id"])  # type: ignore[index]

        # Set cookie
        cookie_name = os.getenv("AUTH_COOKIE_NAME", "ledd_auth")
        cookie_opts = _cookie_settings()

        # Validate stored continue URL before redirecting
        stored = state_doc.get("continue")
        continue_url = (
            stored if (isinstance(stored, str) and _is_allowed_redirect_url(stored)) else _pick_continue_url(request)
        )
        response = redirect(continue_url)
        response.add_cookie(cookie_name, session_id, **cookie_opts)
        return response
    except Exception as e:
        logger.exception("Discord callback failed: %s", e)
        return json({"error": "OAuth flow failed"}, status=500)


def _extract_session_id(request) -> Optional[str]:
    cookie_name = os.getenv("AUTH_COOKIE_NAME", "ledd_auth")
    return request.cookies.get(cookie_name)


@app.get("/me")
async def me(request):
    db = _require_db()
    session_id = _extract_session_id(request)
    if not session_id:
        return json({"error": "Not authenticated"}, status=401)
    user = get_user_by_session(db, session_id)
    if not user:
        return json({"error": "Invalid session"}, status=401)
    # Minimal public profile
    return json(
        {
            "discord_id": user.get("discord_id"),
            "username": user.get("username"),
            "global_name": user.get("global_name"),
            "avatar": user.get("avatar"),
        }
    )


@app.post("/logout")
async def logout(request):
    db = _require_db()
    session_id = _extract_session_id(request)
    if session_id:
        delete_session(db, session_id)
    cookie_name = os.getenv("AUTH_COOKIE_NAME", "ledd_auth")
    cookie_opts = _cookie_settings()
    # Choose redirect or JSON based on client intent
    continue_to = request.args.get("continue") or request.headers.get("referer")
    wants_html = "text/html" in (request.headers.get("accept", "").lower())
    if continue_to and isinstance(continue_to, str) and _is_allowed_redirect_url(continue_to):
        response = redirect(continue_to)
    elif wants_html:
        response = redirect(f"https://{_allowed_return_hosts()[0]}/")
    else:
        # Default API-style response
        response = json({"ok": True})
    # Clear cookie by setting expires in the past and empty value
    expires_dt = datetime(1970, 1, 1, tzinfo=timezone.utc)
    response.add_cookie(cookie_name, "", expires=expires_dt, max_age=0, **cookie_opts)
    return response


@app.get("/logout")
async def logout_get(request):
    db = _require_db()
    session_id = _extract_session_id(request)
    if session_id:
        delete_session(db, session_id)
    cookie_name = os.getenv("AUTH_COOKIE_NAME", "ledd_auth")
    cookie_opts = _cookie_settings()
    # Choose a safe redirect destination
    target = request.args.get("continue") or request.headers.get("referer")
    if not (isinstance(target, str) and _is_allowed_redirect_url(target)):
        target = f"https://{_allowed_return_hosts()[0]}/"
    response = redirect(target)
    expires_dt = datetime(1970, 1, 1, tzinfo=timezone.utc)
    response.add_cookie(cookie_name, "", expires=expires_dt, max_age=0, **cookie_opts)
    # Return the redirect response that also clears the cookie
    return response


if __name__ == "__main__":
    # This will typically run behind a reverse proxy for auth.ledd.live
    port = int(os.getenv("AUTH_SERVER_PORT", "3100"))
    app.run(host="0.0.0.0", port=port, auto_reload=True)
