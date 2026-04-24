"""
Enphase Enlighten authentication: login, session cookie, CSRF token refresh.
"""

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://enlighten.enphaseenergy.com"
LOGIN_URL = f"{BASE_URL}/login/login"
TOKEN_URL = f"{BASE_URL}/service/auth_ms_enho/api/v1/session/token"


class EnphaseAuth:
    def __init__(self):
        self.email = os.getenv("ENPHASE_EMAIL")
        self.password = os.getenv("ENPHASE_PASSWORD")
        if not self.email or not self.password:
            raise ValueError("ENPHASE_EMAIL and ENPHASE_PASSWORD must be set in .env")
        self._client: httpx.AsyncClient | None = None
        self._csrf_token: str | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=BASE_URL,
                follow_redirects=True,
                timeout=30.0,
            )
        return self._client

    async def login(self) -> None:
        client = await self._get_client()
        resp = await client.post(
            LOGIN_URL,
            data={"user[email]": self.email, "user[password]": self.password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        self._csrf_token = None  # force refresh after login

    async def get_csrf_token(self) -> str:
        client = await self._get_client()
        # Prefer the XSRF-TOKEN cookie (set by Enlighten after login).
        # Browser JS cannot read it (HttpOnly), but the Python httpx jar can.
        # The /profile/ write endpoint validates this cookie value, not the JWT.
        xsrf = client.cookies.get("XSRF-TOKEN")
        if xsrf:
            self._csrf_token = xsrf
            return xsrf
        # No cookie yet — establish a session first.
        await self.login()
        xsrf = client.cookies.get("XSRF-TOKEN")
        if xsrf:
            self._csrf_token = xsrf
            return xsrf
        # Fall back to the JWT session token (older API endpoints may accept it).
        resp = await client.get(TOKEN_URL)
        if resp.status_code == 401:
            await self.login()
            resp = await client.get(TOKEN_URL)
        resp.raise_for_status()
        token = resp.text.strip().strip('"')
        self._csrf_token = token
        return token

    async def request(
        self,
        method: str,
        url: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        retry: bool = True,
    ) -> httpx.Response:
        client = await self._get_client()

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": f"{BASE_URL}/",
            "Origin": BASE_URL,
        }
        if method.upper() in ("POST", "PUT", "PATCH"):
            csrf = await self.get_csrf_token()
            headers["X-XSRF-Token"] = csrf
            headers["Content-Type"] = "application/json"

        resp = await client.request(method, url, json=json, params=params, headers=headers)

        if resp.status_code == 401 and retry:
            await self.login()
            return await self.request(method, url, json=json, params=params, retry=False)

        resp.raise_for_status()
        return resp

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton used by the rest of the app
_auth: EnphaseAuth | None = None


def get_auth() -> EnphaseAuth:
    global _auth
    if _auth is None:
        _auth = EnphaseAuth()
    return _auth
