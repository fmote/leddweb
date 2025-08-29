# leddweb

Two Sanic apps:

- API app: `main.py` (notes + pages)
- Auth app: `auth_server.py` (Discord OAuth for auth.ledd.live)

Env vars (place in .env):

- MONGODB_URI: base64-encoded connection string
- DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET
- DISCORD_REDIRECT_URI: e.g. https://auth.ledd.live/discord/callback (optional if behind reverse proxy)
- AUTH_COOKIE_DOMAIN: auth.ledd.live (defaults)
- AUTH_COOKIE_NAME: ledd_auth (default)
- AUTH_COOKIE_SECURE: true (default)
- AUTH_SESSION_TTL_DAYS: 30 (default)

Run:

1) API: `python main.py`
2) Auth: `python auth_server.py`
