"""
Tests for call_tool input validation in server.py.
"""
import json
from unittest.mock import AsyncMock, patch

from server import call_tool


# ---------------------------------------------------------------------------
# enphase_set_charge_window — input validation
# ---------------------------------------------------------------------------

@patch("api.set_charge_window", new_callable=AsyncMock)
async def test_charge_window_valid(mock_set):
    mock_set.return_value = {"status": "ok"}
    result = await call_tool("enphase_set_charge_window", {"begin_minutes": 600, "end_minutes": 900})
    payload = json.loads(result[0].text)
    assert payload["success"] is True
    assert payload["begin_minutes"] == 600
    assert payload["end_minutes"] == 900
    mock_set.assert_called_once_with(600, 900)


@patch("api.set_charge_window", new_callable=AsyncMock)
async def test_charge_window_end_before_begin(mock_set):
    result = await call_tool("enphase_set_charge_window", {"begin_minutes": 900, "end_minutes": 600})
    assert "Error" in result[0].text or "error" in result[0].text.lower()
    mock_set.assert_not_called()


@patch("api.set_charge_window", new_callable=AsyncMock)
async def test_charge_window_negative_begin(mock_set):
    result = await call_tool("enphase_set_charge_window", {"begin_minutes": -1, "end_minutes": 600})
    assert "Error" in result[0].text or "error" in result[0].text.lower()
    mock_set.assert_not_called()


@patch("api.set_charge_window", new_callable=AsyncMock)
async def test_charge_window_end_at_midnight(mock_set):
    """1440 is out of range (valid range is 0–1439)."""
    result = await call_tool("enphase_set_charge_window", {"begin_minutes": 600, "end_minutes": 1440})
    assert "Error" in result[0].text or "error" in result[0].text.lower()
    mock_set.assert_not_called()


@patch("api.set_charge_window", new_callable=AsyncMock)
async def test_charge_window_equal_begin_end(mock_set):
    result = await call_tool("enphase_set_charge_window", {"begin_minutes": 600, "end_minutes": 600})
    assert "Error" in result[0].text or "error" in result[0].text.lower()
    mock_set.assert_not_called()
