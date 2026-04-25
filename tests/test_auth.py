"""
Unit tests for auth.py — uses respx to mock httpx calls.
"""
import pytest
import respx
import httpx

from auth import EnphaseAuth, BASE_URL, LOGIN_URL, TOKEN_URL


# ---------------------------------------------------------------------------
# EnphaseAuth constructor
# ---------------------------------------------------------------------------

def test_raises_if_email_missing(monkeypatch):
    monkeypatch.delenv("ENPHASE_EMAIL", raising=False)
    monkeypatch.setenv("ENPHASE_PASSWORD", "secret")
    with pytest.raises(ValueError, match="ENPHASE_EMAIL"):
        EnphaseAuth()


def test_raises_if_password_missing(monkeypatch):
    monkeypatch.setenv("ENPHASE_EMAIL", "test@example.com")
    monkeypatch.delenv("ENPHASE_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="ENPHASE_PASSWORD"):
        EnphaseAuth()


def test_raises_if_both_missing(monkeypatch):
    monkeypatch.delenv("ENPHASE_EMAIL", raising=False)
    monkeypatch.delenv("ENPHASE_PASSWORD", raising=False)
    with pytest.raises(ValueError):
        EnphaseAuth()


# ---------------------------------------------------------------------------
# get_csrf_token — cookie path (BP-XSRF-Token)
# ---------------------------------------------------------------------------

@respx.mock
async def test_get_csrf_token_uses_cookie_when_present():
    # login() GETs the login page first, then POSTs credentials
    respx.get(LOGIN_URL).mock(return_value=httpx.Response(200))
    login_post = respx.post(LOGIN_URL).mock(
        return_value=httpx.Response(200, headers={"Set-Cookie": "BP-XSRF-Token=cookie-xsrf; Path=/"})
    )

    a = EnphaseAuth()
    # Seed cookie manually as if set-cookie header arrived
    client = await a._get_client()
    client.cookies.set("BP-XSRF-Token", "cookie-xsrf", domain="enlighten.enphaseenergy.com")

    token = await a.get_csrf_token()
    assert token == "cookie-xsrf"


@respx.mock
async def test_get_csrf_token_falls_back_to_jwt_when_no_cookie():
    # No BP-XSRF-Token cookie → login → still no cookie → fall back to JWT
    respx.get(LOGIN_URL).mock(return_value=httpx.Response(200))
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(200))
    respx.get(TOKEN_URL).mock(return_value=httpx.Response(200, text='"jwt-token"'))

    a = EnphaseAuth()
    token = await a.get_csrf_token()

    assert token == "jwt-token"
    assert a._csrf_token == "jwt-token"


@respx.mock
async def test_get_csrf_token_401_on_jwt_triggers_login_then_retries():
    respx.get(LOGIN_URL).mock(return_value=httpx.Response(200))
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(200))
    token_route = respx.get(TOKEN_URL).mock(
        side_effect=[
            httpx.Response(401),
            httpx.Response(200, text='"retry-token"'),
        ]
    )

    a = EnphaseAuth()
    token = await a.get_csrf_token()

    assert token == "retry-token"
    assert token_route.call_count == 2


# ---------------------------------------------------------------------------
# request — POST adds X-XSRF-Token and X-BP-XSRF-Token headers
# ---------------------------------------------------------------------------

@respx.mock
async def test_request_post_adds_csrf_headers():
    respx.get(LOGIN_URL).mock(return_value=httpx.Response(200))
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(200))
    respx.get(TOKEN_URL).mock(return_value=httpx.Response(200, text='"csrf-abc"'))
    target = respx.post(f"{BASE_URL}/some/endpoint").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    a = EnphaseAuth()
    resp = await a.request("POST", "/some/endpoint", json={"x": 1})

    assert resp.status_code == 200
    sent_headers = target.calls[0].request.headers
    assert sent_headers.get("x-xsrf-token") == "csrf-abc"
    assert sent_headers.get("x-bp-xsrf-token") == "csrf-abc"


# ---------------------------------------------------------------------------
# request — 401 retry calls login then re-issues the request
# ---------------------------------------------------------------------------

@respx.mock
async def test_request_retries_after_401():
    respx.get(LOGIN_URL).mock(return_value=httpx.Response(200))
    login_route = respx.post(LOGIN_URL).mock(return_value=httpx.Response(200))

    get_route = respx.get(f"{BASE_URL}/some/data").mock(
        side_effect=[
            httpx.Response(401),
            httpx.Response(200, json={"data": 42}),
        ]
    )

    a = EnphaseAuth()
    resp = await a.request("GET", "/some/data")

    assert resp.json() == {"data": 42}
    assert login_route.called
    assert get_route.call_count == 2


# ---------------------------------------------------------------------------
# request — non-401 HTTP errors are raised
# ---------------------------------------------------------------------------

@respx.mock
async def test_request_raises_on_non_401_error():
    respx.get(f"{BASE_URL}/bad/endpoint").mock(return_value=httpx.Response(500))

    a = EnphaseAuth()
    with pytest.raises(httpx.HTTPStatusError):
        await a.request("GET", "/bad/endpoint")
