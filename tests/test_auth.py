"""
Unit tests for auth.py — uses respx to mock httpx calls.
"""
import sys
import os
import pytest
import respx
import httpx

# Ensure the project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import auth as auth_module
from auth import EnphaseAuth, BASE_URL, LOGIN_URL, TOKEN_URL


@pytest.fixture(autouse=True)
def reset_auth_singleton():
    """Reset the module-level singleton between tests."""
    auth_module._auth = None
    yield
    auth_module._auth = None


@pytest.fixture
def valid_env(monkeypatch):
    monkeypatch.setenv("ENPHASE_EMAIL", "test@example.com")
    monkeypatch.setenv("ENPHASE_PASSWORD", "secret")


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
# get_csrf_token
# ---------------------------------------------------------------------------

@respx.mock
async def test_get_csrf_token_success(valid_env):
    respx.get(TOKEN_URL).mock(return_value=httpx.Response(200, text='"my-token"'))

    a = EnphaseAuth()
    token = await a.get_csrf_token()

    assert token == "my-token"
    assert a._csrf_token == "my-token"


@respx.mock
async def test_get_csrf_token_401_triggers_login_then_retries(valid_env):
    # First call → 401, second call → 200
    token_route = respx.get(TOKEN_URL).mock(
        side_effect=[
            httpx.Response(401),
            httpx.Response(200, text='"retry-token"'),
        ]
    )
    login_route = respx.post(LOGIN_URL).mock(return_value=httpx.Response(200))

    a = EnphaseAuth()
    token = await a.get_csrf_token()

    assert token == "retry-token"
    assert login_route.called
    assert token_route.call_count == 2


# ---------------------------------------------------------------------------
# request — POST adds X-XSRF-Token header
# ---------------------------------------------------------------------------

@respx.mock
async def test_request_post_adds_csrf_header(valid_env):
    respx.get(TOKEN_URL).mock(return_value=httpx.Response(200, text='"csrf-abc"'))
    target = respx.post(f"{BASE_URL}/some/endpoint").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    a = EnphaseAuth()
    resp = await a.request("POST", "/some/endpoint", json={"x": 1})

    assert resp.status_code == 200
    sent_headers = target.calls[0].request.headers
    assert sent_headers.get("x-xsrf-token") == "csrf-abc"


# ---------------------------------------------------------------------------
# request — 401 retry calls login then re-issues the request
# ---------------------------------------------------------------------------

@respx.mock
async def test_request_retries_after_401(valid_env):
    respx.get(TOKEN_URL).mock(return_value=httpx.Response(200, text='"tok"'))
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
async def test_request_raises_on_non_401_error(valid_env):
    respx.get(f"{BASE_URL}/bad/endpoint").mock(return_value=httpx.Response(500))

    a = EnphaseAuth()
    with pytest.raises(httpx.HTTPStatusError):
        await a.request("GET", "/bad/endpoint")
