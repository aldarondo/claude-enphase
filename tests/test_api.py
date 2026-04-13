"""
Unit tests for api.py — mocks EnphaseAuth.request via AsyncMock.
"""
import sys
import os
import pytest
from unittest.mock import AsyncMock, patch
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import api as api_module
import auth as auth_module
from api import (
    SITE_ID,
    USER_ID,
    VALID_PROFILES,
    get_latest_power,
    get_today_stats,
    get_savings,
    get_battery_settings,
    set_battery_profile,
    get_tariff,
    get_alerts,
    get_status_summary,
)


def _make_response(json_data: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=json_data)


@pytest.fixture(autouse=True)
def reset_auth_singleton(monkeypatch):
    """Reset module-level _auth singleton (lives in auth.py) so each test starts fresh."""
    monkeypatch.setattr(auth_module, "_auth", None)
    # Also set env vars so EnphaseAuth() can be constructed if needed
    monkeypatch.setenv("ENPHASE_EMAIL", "test@example.com")
    monkeypatch.setenv("ENPHASE_PASSWORD", "secret")


@pytest.fixture
def mock_request():
    """Patches EnphaseAuth.request with an AsyncMock and returns it."""
    with patch("auth.EnphaseAuth.request", new_callable=AsyncMock) as m:
        yield m


# ---------------------------------------------------------------------------
# get_latest_power
# ---------------------------------------------------------------------------

async def test_get_latest_power_calls_correct_endpoint(mock_request):
    payload = {"production": 3200}
    mock_request.return_value = _make_response(payload)

    result = await get_latest_power()

    assert result == payload
    mock_request.assert_called_once_with("GET", f"/app-api/{SITE_ID}/get_latest_power")


# ---------------------------------------------------------------------------
# get_today_stats
# ---------------------------------------------------------------------------

async def test_get_today_stats_calls_correct_endpoint(mock_request):
    payload = {"energy_produced": 12000}
    mock_request.return_value = _make_response(payload)

    result = await get_today_stats()

    assert result == payload
    mock_request.assert_called_once_with("GET", f"/pv/systems/{SITE_ID}/today")


# ---------------------------------------------------------------------------
# get_savings
# ---------------------------------------------------------------------------

async def test_get_savings_passes_correct_params(mock_request):
    payload = {"net_cost": -1.50}
    mock_request.return_value = _make_response(payload)

    result = await get_savings("2025-06-15", "MONTH")

    assert result == payload
    mock_request.assert_called_once_with(
        "GET",
        f"/service/savings/systems/{SITE_ID}/savings",
        params={"resolution": "MONTH", "date": "2025-06-15"},
    )


async def test_get_savings_default_resolution(mock_request):
    mock_request.return_value = _make_response({})

    await get_savings("2025-06-15")

    _, call_kwargs = mock_request.call_args
    assert call_kwargs["params"]["resolution"] == "DAY"


# ---------------------------------------------------------------------------
# get_battery_settings
# ---------------------------------------------------------------------------

async def test_get_battery_settings_calls_correct_endpoint(mock_request):
    payload = {"usage": "cost_savings", "backupReserve": 20}
    mock_request.return_value = _make_response(payload)

    result = await get_battery_settings()

    assert result == payload
    mock_request.assert_called_once_with(
        "GET",
        f"/service/batteryConfig/api/v1/batterySettings/{SITE_ID}",
        params={"source": "enho", "userId": USER_ID},
    )


# ---------------------------------------------------------------------------
# set_battery_profile
# ---------------------------------------------------------------------------

async def test_set_battery_profile_posts_to_correct_endpoint(mock_request):
    payload = {"status": "ok"}
    mock_request.return_value = _make_response(payload)

    result = await set_battery_profile("self-consumption")

    assert result == payload
    mock_request.assert_called_once_with(
        "POST",
        f"/service/batteryConfig/api/v1/batterySettings/{SITE_ID}",
        json={"usage": "self-consumption", "source": "enho", "userId": int(USER_ID)},
    )


async def test_set_battery_profile_raises_for_invalid_profile(mock_request):
    with pytest.raises(ValueError, match="Invalid profile"):
        await set_battery_profile("turbo_mode")

    mock_request.assert_not_called()


# ---------------------------------------------------------------------------
# get_tariff
# ---------------------------------------------------------------------------

async def test_get_tariff_calls_correct_endpoint(mock_request):
    payload = {"rates": []}
    mock_request.return_value = _make_response(payload)

    result = await get_tariff()

    assert result == payload
    mock_request.assert_called_once_with(
        "GET",
        f"/app-api/{SITE_ID}/tariff.json",
        params={"country": "us"},
    )


# ---------------------------------------------------------------------------
# get_alerts
# ---------------------------------------------------------------------------

async def test_get_alerts_calls_correct_endpoint(mock_request):
    payload = {"alerts": []}
    mock_request.return_value = _make_response(payload)

    result = await get_alerts()

    assert result == payload
    mock_request.assert_called_once_with(
        "GET",
        f"/app-api/{SITE_ID}/new_articles_alert.json",
    )


# ---------------------------------------------------------------------------
# get_status_summary — aggregation
# ---------------------------------------------------------------------------

async def test_get_status_summary_aggregates_correctly(mock_request):
    power_payload = {"production_w": 4500, "consumption_w": 2100}
    battery_payload = {
        "usage": "cost_savings",
        "backupReserve": 20,
        "stormGuard": False,
        "chargeFromGrid": True,
    }
    today_payload = {
        "energy_produced": 18000,
        "energy_consumed": 9000,
        "energy_exported": 5000,
        "energy_imported": 0,
        "energy_charged": 3000,
        "energy_discharged": 0,
        "battery_soc": 85,
        "intervals": [{"soc": 85}],
    }

    # Calls happen in order: get_latest_power, get_battery_settings, get_today_stats
    mock_request.side_effect = [
        _make_response(power_payload),
        _make_response(battery_payload),
        _make_response(today_payload),
    ]

    result = await get_status_summary()

    assert "current_power_w" in result
    assert "battery" in result
    assert "today" in result

    assert result["current_power_w"] == power_payload
    assert result["battery"]["profile"] == "cost_savings"
    assert result["battery"]["backup_reserve_pct"] == 20
    assert result["battery"]["storm_guard"] is False
    assert result["battery"]["charge_from_grid"] is True

    assert result["today"]["solar_produced_wh"] == 18000
    assert result["today"]["consumed_wh"] == 9000
    assert result["today"]["battery_soc_pct"] == 85
