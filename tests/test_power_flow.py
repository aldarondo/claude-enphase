"""
Tests for _find_active_rate, _demand_charge_context, _buyback_rate — pure functions, no I/O.
Tariff fixture mirrors the live APS R-3 TOU structure.
"""
from datetime import datetime
import pytz
import pytest

from server import _find_active_rate, _demand_charge_context, _buyback_rate, _in_season

ARIZONA = pytz.timezone("US/Arizona")

# ---------------------------------------------------------------------------
# Minimal tariff fixture (matches live APS R-3 structure)
# ---------------------------------------------------------------------------

TARIFF = {
    "purchase": {
        "seasons": [
            {
                "id": "summer",
                "startMonth": "5",
                "endMonth": "10",
                "days": [
                    {
                        "id": "weekdays",
                        "days": [1, 2, 3, 4, 5],
                        "periods": [
                            {"id": "peak",     "startTime": 960,  "endTime": 1139, "rate": "0.14375", "type": "peak"},
                            {"id": "off-peak", "startTime": "",   "endTime": "",   "rate": "0.04849", "type": "off-peak"},
                        ],
                    },
                    {
                        "id": "weekend",
                        "days": [6, 7],
                        "periods": [
                            {"id": "period-1", "startTime": 0,    "endTime": 1439, "rate": "0.06091", "type": "peak"},
                            {"id": "off-peak", "startTime": "",   "endTime": "",   "rate": "0.0",     "type": "off-peak"},
                        ],
                    },
                ],
            },
            {
                "id": "winter",
                "startMonth": "11",
                "endMonth": "4",
                "days": [
                    {
                        "id": "weekdays",
                        "days": [1, 2, 3, 4, 5],
                        "periods": [
                            {"id": "period-0", "startTime": 0,    "endTime": 599,  "rate": "0.04854", "type": "mid-peak"},
                            {"id": "period-2", "startTime": 900,  "endTime": 959,  "rate": "0.06086", "type": "mid-peak"},
                            {"id": "period-3", "startTime": 960,  "endTime": 1139, "rate": "0.1008",  "type": "peak"},
                            {"id": "period-1", "startTime": 1140, "endTime": 1439, "rate": "0.06086", "type": "mid-peak"},
                            {"id": "off-peak", "startTime": "",   "endTime": "",   "rate": "0.03643", "type": "off-peak"},
                        ],
                    },
                    {
                        "id": "weekend",
                        "days": [6, 7],
                        "periods": [
                            {"id": "period-1", "startTime": 0,    "endTime": 1439, "rate": "0.06086", "type": "peak"},
                            {"id": "off-peak", "startTime": "",   "endTime": "",   "rate": "0.0",     "type": "off-peak"},
                        ],
                    },
                ],
            },
        ],
        "demandCharge": {
            "demandChargeSeasons": [
                {
                    "id": "summer",
                    "startMonth": "5",
                    "endMonth": "10",
                    "days": [{"id": "weekdays", "days": [1, 2, 3, 4, 5],
                              "periods": [{"id": "period-1", "startTime": "960", "endTime": "1139", "rate": "19.58500", "type": "ON_PEAK"}]}],
                },
                {
                    "id": "winter",
                    "startMonth": "11",
                    "endMonth": "4",
                    "days": [{"id": "weekdays", "days": [1, 2, 3, 4, 5],
                              "periods": [{"id": "period-1", "startTime": "960", "endTime": "1139", "rate": "13.74700", "type": "ON_PEAK"}]}],
                },
            ]
        },
    },
    "buyback": {
        "seasons": [
            {"id": "default", "startMonth": "1", "endMonth": "12",
             "days": [{"id": "week", "days": [1,2,3,4,5,6,7],
                       "periods": [{"id": "off-peak", "startTime": "", "endTime": "", "rate": "0.08465", "type": "off-peak"}]}]}
        ]
    },
}


def _az(month: int, weekday: int, hour: int, minute: int = 0) -> datetime:
    """Build an Arizona-aware datetime for the given month/weekday/hour."""
    known_mondays = {1: 5, 2: 2, 3: 2, 4: 7, 5: 5, 6: 2, 7: 7, 8: 4, 9: 1, 10: 6, 11: 3, 12: 1}
    day = known_mondays[month] + weekday  # weekday 0=Mon
    return ARIZONA.localize(datetime(2026, month, day, hour, minute))


# ---------------------------------------------------------------------------
# _in_season
# ---------------------------------------------------------------------------

def test_in_season_summer():
    summer = {"startMonth": "5", "endMonth": "10"}
    assert _in_season(summer, 7)
    assert not _in_season(summer, 11)


def test_in_season_winter_wraps():
    winter = {"startMonth": "11", "endMonth": "4"}
    assert _in_season(winter, 1)   # January
    assert _in_season(winter, 11)  # November
    assert _in_season(winter, 4)   # April
    assert not _in_season(winter, 5)


# ---------------------------------------------------------------------------
# _find_active_rate
# ---------------------------------------------------------------------------

def test_winter_weekday_peak():
    now = _az(4, 0, 16, 30)  # April Monday 4:30pm (960–1139)
    r = _find_active_rate(TARIFF, now)
    assert r["type"] == "peak"
    assert r["rate_per_kwh"] == pytest.approx(0.1008)
    assert r["season"] == "winter"


def test_winter_weekday_mid_peak_morning():
    now = _az(4, 0, 8, 0)  # April Monday 8am (period-0: 0–599)
    r = _find_active_rate(TARIFF, now)
    assert r["type"] == "mid-peak"
    assert r["rate_per_kwh"] == pytest.approx(0.04854)


def test_winter_weekday_off_peak_fallback():
    now = _az(4, 0, 11, 0)  # April Monday 11am (600–899 = off-peak fallback)
    r = _find_active_rate(TARIFF, now)
    assert r["type"] == "off-peak"
    assert r["rate_per_kwh"] == pytest.approx(0.03643)


def test_winter_weekend():
    now = _az(4, 5, 14, 0)  # April Saturday 2pm
    r = _find_active_rate(TARIFF, now)
    assert r["period_id"] == "period-1"
    assert r["rate_per_kwh"] == pytest.approx(0.06086)


def test_summer_weekday_peak():
    now = _az(7, 0, 17, 0)  # July Monday 5pm
    r = _find_active_rate(TARIFF, now)
    assert r["type"] == "peak"
    assert r["rate_per_kwh"] == pytest.approx(0.14375)


def test_summer_weekday_off_peak():
    now = _az(7, 0, 10, 0)  # July Monday 10am
    r = _find_active_rate(TARIFF, now)
    assert r["type"] == "off-peak"
    assert r["rate_per_kwh"] == pytest.approx(0.04849)


# ---------------------------------------------------------------------------
# _demand_charge_context
# ---------------------------------------------------------------------------


def test_demand_in_window_winter():
    now = _az(4, 0, 16, 0)  # April Monday 4pm
    d = _demand_charge_context(TARIFF, now)
    assert d["in_window"] is True
    assert d["rate_per_kw"] == pytest.approx(13.747)
    assert d["season"] == "winter"


def test_demand_not_in_window():
    now = _az(4, 0, 10, 0)  # April Monday 10am
    d = _demand_charge_context(TARIFF, now)
    assert d["in_window"] is False


def test_demand_no_window_on_weekend():
    now = _az(4, 5, 16, 0)  # April Saturday 4pm — no demand charge
    d = _demand_charge_context(TARIFF, now)
    assert d is None


def test_demand_window_summer_rate():
    now = _az(7, 0, 17, 0)  # July Monday 5pm
    d = _demand_charge_context(TARIFF, now)
    assert d["in_window"] is True
    assert d["rate_per_kw"] == pytest.approx(19.585)


# ---------------------------------------------------------------------------
# _buyback_rate
# ---------------------------------------------------------------------------

def test_buyback_rate():
    assert _buyback_rate(TARIFF) == pytest.approx(0.08465)


def test_buyback_rate_missing():
    assert _buyback_rate({}) is None
