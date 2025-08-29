from __future__ import annotations

import aiohttp
import urllib.parse
from typing import Dict, Any


DISCORD_API = "https://discord.com/api"
AUTHORIZE_URL = "https://discord.com/oauth2/authorize"


def build_authorize_url(*, client_id: str, state: str, redirect_uri: str, scope: str) -> str:
    base = AUTHORIZE_URL
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        # optional: prompt=consent to force re-consent
    }
    return f"{base}?{urllib.parse.urlencode(params)}"


async def exchange_code_for_token(*, code: str, client_id: str, client_secret: str, redirect_uri: str) -> Dict[str, Any]:
    token_url = f"{DISCORD_API}/oauth2/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, data=data, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Token exchange failed: {resp.status} {text}")
            return await resp.json()


async def fetch_discord_user(access_token: str) -> Dict[str, Any]:
    me_url = f"{DISCORD_API}/users/@me"
    headers = {"Authorization": f"Bearer {access_token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(me_url, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Fetch user failed: {resp.status} {text}")
            return await resp.json()
