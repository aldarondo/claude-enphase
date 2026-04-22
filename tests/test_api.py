"""
Unit tests for api.py — mocks EnphaseAuth.request via AsyncMock.
"""
import pytest
from unittest.mock import AsyncMock, patch
import httpx

from api import (
    SITE_ID,
    USER_ID,
    VALID_PROFILES,
    get_latest_power,
    get_today_stats,
    get_savings,
    get_battery_settings,
    set_battery_profile,
    set_charge_window,
    get_tariff,
    get_alerts,
    get_status_summary,
    get_weather,
    get_site_settings,
    get_grid_status,
)


def _make_response(json_data: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=json_data)


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
# set_charge_window
# ---------------------------------------------------------------------------

async def test_set_charge_window_posts_correct_payload(mock_request):
    payload = {"status": "ok"}
    mock_request.return_value = _make_response(payload)

    result = await set_charge_window(600, 900)

    assert result == payload
    mock_request.assert_called_once_with(
        "POST",
        f"/service/batteryConfig/api/v1/batterySettings/{SITE_ID}",
        json={"chargeBeginTime": 600, "chargeEndTime": 900, "source": "enho", "userId": int(USER_ID)},
    )


async def test_set_charge_window_summer_constants(mock_request):
    from server import SUMMER_CHARGE_BEGIN, SUMMER_CHARGE_END
    mock_request.return_value = _make_response({})
    await set_charge_window(SUMMER_CHARGE_BEGIN, SUMMER_CHARGE_END)
    _, kwargs = mock_request.call_args
    assert kwargs["json"]["chargeBeginTime"] == 720   # noon
    assert kwargs["json"]["chargeEndTime"] == 900     # 3pm


async def test_set_charge_window_winter_constants(mock_request):
    from server import WINTER_CHARGE_BEGIN, WINTER_CHARGE_END
    mock_request.return_value = _make_response({})
    await set_charge_window(WINTER_CHARGE_BEGIN, WINTER_CHARGE_END)
    _, kwargs = mock_request.call_args
    assert kwargs["json"]["chargeBeginTime"] == 600   # 10am
    assert kwargs["json"]["chargeEndTime"] == 900     # 3pm


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


# ---------------------------------------------------------------------------
# get_weather
# ---------------------------------------------------------------------------

async def test_get_weather_calls_correct_endpoint(mock_request):
    payload = {"temperature": 98, "conditions": "sunny"}
    mock_request.return_value = _make_response(payload)

    result = await get_weather()

    assert result == payload
    mock_request.assert_called_once_with("GET", f"/app-api/{SITE_ID}/weather")


# ---------------------------------------------------------------------------
# get_site_settings
# ---------------------------------------------------------------------------

async def test_get_site_settings_calls_correct_endpoint(mock_request):
    payload = {"timezone": "America/Phoenix"}
    mock_request.return_value = _make_response(payload)

    result = await get_site_settings()

    assert result == payload
    mock_request.assert_called_once_with(
        "GET",
        f"/service/batteryConfig/api/v1/siteSettings/{SITE_ID}",
        params={"userId": USER_ID},
    )


# ---------------------------------------------------------------------------
# get_grid_status
# ---------------------------------------------------------------------------

async def test_get_grid_status_calls_correct_endpoint(mock_request):
    payload = {"grid_status": "on"}
    mock_request.return_value = _make_response(payload)

    result = await get_grid_status()

    assert result == payload
    mock_request.assert_called_once_with("GET", f"/app-api/{SITE_ID}/grid_control_check.json")


# ---------------------------------------------------------------------------
# set_charge_window — tool handler validation (guard lives in server.py call_tool)
# ---------------------------------------------------------------------------

async def test_set_charge_window_valid_range(mock_request):
    mock_request.return_value = _make_response({"status": "ok"})
    result = await set_charge_window(0, 1439)
    _, kwargs = mock_request.call_args
    assert kwargs["json"]["chargeBeginTime"] == 0
    assert kwargs["json"]["chargeEndTime"] == 1439
