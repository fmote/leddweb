from sanic import Sanic
from sanic.response import json, html
from sanic.exceptions import NotFound
from sanic.response import file
from pathlib import Path
from funcs.connectDB import connect_to_mongodb
from funcs.notes import (
    create_note_indexes,
    get_user_note,
    set_user_note,
    delete_user_note,
    to_api,
)
from funcs.auth_store import get_user_by_session
import os
from urllib.parse import quote
app = Sanic("Ledd")
BASE_DIR = Path(__file__).resolve().parent
PAGES_DIR = BASE_DIR / "pages"

# Shared-session settings (must match auth_server)
AUTH_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "ledd_auth")

@app.listener("before_server_start")
async def setup_db(app, loop):
    client, db = connect_to_mongodb()
    if db is not None:
        create_note_indexes(db)
        app.ctx.db = db
        app.ctx.client = client
        app.ctx.db_ready = True
    else:
        app.ctx.db_ready = False

# Attach user from session cookie, if present
@app.middleware("request")
async def attach_user(request):
    db = getattr(app.ctx, "db", None)
    if db is None:
        return
    session_id = request.cookies.get(AUTH_COOKIE_NAME)
    if not session_id:
        return
    user = get_user_by_session(db, session_id)
    if user:
        request.ctx.user = {
            "discord_id": user.get("discord_id"),
            "username": user.get("username"),
            "global_name": user.get("global_name"),
            "avatar": user.get("avatar"),
            "discriminator": user.get("discriminator"),
        }

@app.route("/")
async def home(request):
        user = getattr(request.ctx, "user", None)

        # Build continue URL back to this page
        scheme = "https" if request.headers.get("x-forwarded-proto", request.scheme) == "https" else "http"
        host = request.headers.get("x-forwarded-host", request.host)
        continue_url = f"{scheme}://{host}{request.path}"
        login_url = f"https://admin.ledd.live/discord/login?continue={quote(continue_url, safe='')}"

        def avatar_url(u):
                did = u.get("discord_id")
                ava = u.get("avatar")
                discrim = u.get("discriminator") or "0"
                if did and ava:
                        return f"https://cdn.discordapp.com/avatars/{did}/{ava}.png?size=128"
                try:
                        idx = int(discrim) % 5
                except Exception:
                        idx = 0
                return f"https://cdn.discordapp.com/embed/avatars/{idx}.png"

        if user:
                avatar = avatar_url(user)
                username = user.get("global_name") or user.get("username") or "User"
                body = f"""
                <!DOCTYPE html>
                <html lang=\"en\">
                <head>
                    <meta charset=\"utf-8\" />
                    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
                    <title>Welcome • dev.ledd.live</title>
                    <style>
                        :root {{ --bg:#0b0f16; --text:#e6eefc; --muted:#9bb0c9; --accent:#4da3ff }}
                        html, body {{ height: 100%; }}
                        body {{ margin:0; display:grid; place-items:center; background:var(--bg); color:var(--text); font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif; }}
                        .card {{ width:min(680px,92vw); background:#111827; border:1px solid rgba(255,255,255,0.08); border-radius:16px; padding:28px; box-shadow:0 10px 40px rgba(0,0,0,0.35); }}
                        .row {{ display:flex; gap:20px; align-items:center; }}
                        .pfp {{ width:84px; height:84px; border-radius:50%; border:2px solid rgba(255,255,255,0.2); box-shadow:0 6px 20px rgba(0,0,0,0.35); }}
                        h1 {{ margin:0 0 6px; font-size:24px; }}
                        p {{ margin:0; color:var(--muted); }}
                        .actions {{ margin-top:22px; display:flex; gap:12px; }}
                        .btn {{ display:inline-flex; align-items:center; gap:10px; padding:10px 14px; border-radius:10px; border:1px solid rgba(255,255,255,0.1); color:#081220; text-decoration:none; background:linear-gradient(135deg,#4da3ff,#7cc4ff); }}
                        .btn:hover {{ filter:brightness(0.98); }}
                    </style>
                </head>
                <body>
                    <main class=\"card\">
                        <div class=\"row\">
                            <img class=\"pfp\" src=\"{avatar}\" alt=\"avatar\"/>
                            <div>
                                <h1>Welcome, {username}</h1>
                                <p>You’re signed in on dev.ledd.live via Discord.</p>
                            </div>
                        </div>
                        <div class=\"actions\">
                            <a class=\"btn\" href=\"/me\">View /me</a>
                            <form method=\"post\" action=\"https://admin.ledd.live/logout\">
                                <button class=\"btn\" type=\"submit\">Logout</button>
                            </form>
                        </div>
                    </main>
                </body>
                </html>
                """
                return html(body)

        # Not authenticated → show login CTA
        body = f"""
        <!DOCTYPE html>
        <html lang=\"en\">
        <head>
            <meta charset=\"utf-8\" />
            <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
            <title>dev.ledd.live • Sign in</title>
            <style>
                :root {{ --bg:#0b0f16; --text:#e6eefc; --muted:#9bb0c9; --accent:#4da3ff }}
                html, body {{ height: 100%; }}
                body {{ margin:0; display:grid; place-items:center; background:var(--bg); color:var(--text); font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif; }}
                .card {{ width:min(640px,92vw); background:#111827; border-radius:16px; padding:28px; border:1px solid rgba(255,255,255,0.08); box-shadow:0 10px 40px rgba(0,0,0,0.35); }}
                h1 {{ margin:0 0 10px; font-size:24px; }}
                p {{ margin:0 0 18px; color:var(--muted); }}
                .btn {{ display:inline-flex; align-items:center; gap:10px; padding:12px 16px; border-radius:10px; border:1px solid rgba(255,255,255,0.12); color:#081220; text-decoration:none; background:linear-gradient(135deg,#4da3ff,#7cc4ff); }}
                .btn:hover {{ filter:brightness(0.98); }}
            </style>
        </head>
        <body>
            <main class=\"card\">
                <h1>Welcome to dev.ledd.live</h1>
                <p>Sign in with Discord to continue.</p>
                <a class=\"btn\" href=\"{login_url}\">Login with Discord</a>
            </main>
        </body>
        </html>
        """
        return html(body)



@app.route("/ping")
async def ping(request):
    return json({"status": "ok"})

@app.get("/me")
async def whoami(request):
    user = getattr(request.ctx, "user", None)
    if not user:
        return json({"authenticated": False}, status=401)
    return json({"authenticated": True, "user": user})

@app.get("/<user_id:int>/note")
async def note_get(request, user_id: int):
    db = getattr(app.ctx, "db", None)
    if db is None:
        return json({"error": "Database not available"}, status=503)
    doc = get_user_note(db, user_id)
    if not doc:
        return json({"error": "Note not found", "user_id": user_id}, status=404)
    return json(to_api(doc))


@app.put("/<user_id:int>/note")
async def note_put(request, user_id: int):
    db = getattr(app.ctx, "db", None)
    if db is None:
        return json({"error": "Database not available"}, status=503)
    body = request.json or {}
    content = body.get("content")
    if content is None:
        return json({"error": "'content' is required in body"}, status=400)
    doc = set_user_note(db, user_id, content)
    return json(to_api(doc), status=200)


@app.delete("/<user_id:int>/note")
async def note_delete(request, user_id: int):
    db = getattr(app.ctx, "db", None)
    if db is None:
        return json({"error": "Database not available"}, status=503)
    ok = delete_user_note(db, user_id)
    if not ok:
        return json({"deleted": False, "user_id": user_id}, status=404)
    return json({"deleted": True, "user_id": user_id})

## handle 404
@app.exception(NotFound)
async def handle_404(request, exc):
    return json({
        "error": "Not Found",
        "path": request.path,
        "method": request.method,
    }, status=404)

# Serve static HTML pages from /pages/<filename>
@app.get("/pages/<name:str>")
async def serve_page(request, name: str):
    candidate = PAGES_DIR / name
    if candidate.suffix == "":
        candidate = candidate.with_suffix(".html")
    if candidate.is_file():
        return await file(candidate)
    raise NotFound(f"Page not found: {name}")

# Direct route alias for /fmote
@app.get("/fmote")
async def fmote(request):
    candidate = PAGES_DIR / "fmote.html"
    if candidate.is_file():
        return await file(candidate)
    raise NotFound("fmote page not found")

if __name__ == "__main__":
    # Enable auto-reload so changes to this file (like adding routes) restart the server automatically
    app.run(host="0.0.0.0", port=3000, auto_reload=True)
    

