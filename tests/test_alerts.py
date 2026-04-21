"""
Tests for _evaluate_alerts — pure function, no I/O.
"""
import sys
import os
from datetime import datetime
import pytz

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server import _evaluate_alerts

ARIZONA = pytz.timezone("US/Arizona")


def _az(weekday: int, hour: int) -> datetime:
    """Build an Arizona-aware datetime on a specific weekday (0=Mon) and hour."""
    # Pick a known Monday (2026-04-20) as base; offset by weekday
    from datetime import timedelta
    base = ARIZONA.localize(datetime(2026, 4, 20, hour, 0, 0))  # Monday
    return base + timedelta(days=weekday)


# ---------------------------------------------------------------------------
# Demand spike risk
# ---------------------------------------------------------------------------

def test_demand_spike_fires_weekday_noon_low_soc():
    now = _az(0, 12)  # Monday noon
    alerts = _evaluate_alerts(25.0, now)
    types = [a["type"] for a in alerts]
    assert "demand_spike_risk" in types


def test_demand_spike_no_fire_weekend():
    now = _az(5, 12)  # Saturday noon
    alerts = _evaluate_alerts(25.0, now)
    assert not any(a["type"] == "demand_spike_risk" for a in alerts)


def test_demand_spike_no_fire_before_window():
    now = _az(0, 9)  # Monday 9am — before noon lead-up
    alerts = _evaluate_alerts(25.0, now)
    assert not any(a["type"] == "demand_spike_risk" for a in alerts)


def test_demand_spike_no_fire_after_window():
    now = _az(0, 19)  # Monday 7pm — window closed
    alerts = _evaluate_alerts(25.0, now)
    assert not any(a["type"] == "demand_spike_risk" for a in alerts)


def test_demand_spike_no_fire_soc_above_threshold():
    now = _az(0, 14)  # Monday 2pm
    alerts = _evaluate_alerts(35.0, now)  # above default 30
    assert not any(a["type"] == "demand_spike_risk" for a in alerts)


def test_demand_spike_custom_threshold():
    now = _az(0, 14)
    alerts = _evaluate_alerts(40.0, now, demand_window_soc_threshold=50.0)
    assert any(a["type"] == "demand_spike_risk" for a in alerts)


# ---------------------------------------------------------------------------
# Low battery
# ---------------------------------------------------------------------------

def test_low_battery_warning_fires():
    now = _az(0, 10)
    alerts = _evaluate_alerts(15.0, now)
    a = next(x for x in alerts if x["type"] == "low_battery")
    assert a["severity"] == "warning"


def test_low_battery_critical_below_10():
    now = _az(0, 10)
    alerts = _evaluate_alerts(5.0, now)
    a = next(x for x in alerts if x["type"] == "low_battery")
    assert a["severity"] == "critical"


def test_low_battery_no_fire_above_threshold():
    now = _az(0, 10)
    alerts = _evaluate_alerts(25.0, now)
    assert not any(a["type"] == "low_battery" for a in alerts)


def test_low_battery_custom_threshold():
    now = _az(0, 10)
    alerts = _evaluate_alerts(25.0, now, low_soc_threshold=30.0)
    assert any(a["type"] == "low_battery" for a in alerts)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_no_alerts_when_soc_none():
    now = _az(0, 14)
    alerts = _evaluate_alerts(None, now)
    assert alerts == []


def test_both_alerts_can_fire_simultaneously():
    now = _az(0, 14)  # weekday peak window
    alerts = _evaluate_alerts(10.0, now, low_soc_threshold=20.0, demand_window_soc_threshold=30.0)
    types = [a["type"] for a in alerts]
    assert "demand_spike_risk" in types
    assert "low_battery" in types
