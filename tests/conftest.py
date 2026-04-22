"""
Shared pytest fixtures for the enphase test suite.
"""
import pytest
import auth as auth_module


@pytest.fixture(autouse=True)
def enphase_env(monkeypatch):
    """Ensure Enphase credentials are set so EnphaseAuth() can be constructed in any test."""
    monkeypatch.setenv("ENPHASE_EMAIL", "test@example.com")
    monkeypatch.setenv("ENPHASE_PASSWORD", "secret")


@pytest.fixture(autouse=True)
def reset_auth_singleton():
    """Reset the module-level _auth singleton between tests."""
    auth_module._auth = None
    yield
    auth_module._auth = None
