"""
Clean wrappers around the Enphase Enlighten internal web API.
"""

from auth import get_auth

SITE_ID = "3687112"
USER_ID = "3263059"
ENVOY_SERIAL = "202215001910"

VALID_PROFILES = ("self-consumption", "cost_savings", "ai_optimisation", "backup_only", "expert")


async def get_latest_power() -> dict:
    auth = get_auth()
    resp = await auth.request("GET", f"/app-api/{SITE_ID}/get_latest_power")
    return resp.json()


async def get_today_stats() -> dict:
    auth = get_auth()
    resp = await auth.request("GET", f"/pv/systems/{SITE_ID}/today")
    return resp.json()


async def get_savings(date_str: str, resolution: str = "DAY") -> dict:
    auth = get_auth()
    resp = await auth.request(
        "GET",
        f"/service/savings/systems/{SITE_ID}/savings",
        params={"resolution": resolution, "date": date_str},
    )
    return resp.json()


async def get_battery_settings() -> dict:
    auth = get_auth()
    resp = await auth.request(
        "GET",
        f"/service/batteryConfig/api/v1/batterySettings/{SITE_ID}",
        params={"source": "enho", "userId": USER_ID},
    )
    return resp.json()


async def set_charge_window(begin_minutes: int, end_minutes: int) -> dict:
    """Set the charge-from-grid time window. Times are minutes from midnight (AZ time)."""
    from datetime import datetime, timezone
    auth = get_auth()
    # Enphase API migrated from POST to PUT for batterySettings writes.
    # acceptedItcDisclaimer is required by the endpoint; pass current UTC time.
    resp = await auth.request(
        "PUT",
        f"/service/batteryConfig/api/v1/batterySettings/{SITE_ID}",
        params={"userId": USER_ID},
        json={
            "chargeBeginTime": begin_minutes,
            "chargeEndTime": end_minutes,
            "chargeFromGrid": False,
            "acceptedItcDisclaimer": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "chargeFromGridScheduleEnabled": False,
        },
    )
    return resp.json()


async def set_battery_profile(profile: str) -> dict:
    if profile not in VALID_PROFILES:
        raise ValueError(f"Invalid profile '{profile}'. Choose from: {VALID_PROFILES}")
    auth = get_auth()
    # Enphase updated their API: profile changes now go to PUT /profile/ (not POST /batterySettings/).
    resp = await auth.request(
        "PUT",
        f"/service/batteryConfig/api/v1/profile/{SITE_ID}",
        params={"userId": USER_ID},
        json={"profile": profile, "batteryBackupPercentage": 20},
    )
    return resp.json()


async def get_tariff() -> dict:
    auth = get_auth()
    resp = await auth.request(
        "GET",
        f"/app-api/{SITE_ID}/tariff.json",
        params={"country": "us"},
    )
    return resp.json()


async def get_weather() -> dict:
    auth = get_auth()
    resp = await auth.request("GET", f"/app-api/{SITE_ID}/weather")
    return resp.json()


async def get_alerts() -> dict:
    auth = get_auth()
    resp = await auth.request("GET", f"/app-api/{SITE_ID}/new_articles_alert.json")
    return resp.json()


async def get_storm_alert() -> dict:
    auth = get_auth()
    resp = await auth.request(
        "GET",
        f"/service/batteryConfig/api/v1/stormGuard/{SITE_ID}/stormAlert",
        params={"userId": USER_ID},
    )
    return resp.json()


async def get_site_settings() -> dict:
    auth = get_auth()
    resp = await auth.request(
        "GET",
        f"/service/batteryConfig/api/v1/siteSettings/{SITE_ID}",
        params={"userId": USER_ID},
    )
    return resp.json()


async def get_grid_status() -> dict:
    auth = get_auth()
    resp = await auth.request("GET", f"/app-api/{SITE_ID}/grid_control_check.json")
    return resp.json()


async def get_status_summary() -> dict:
    """Aggregates latest_power + today_stats + battery_settings into one status dict."""
    power = await get_latest_power()
    battery = await get_battery_settings()

    today = await get_today_stats()
    intervals = today.get("intervals", [])
    latest_interval = intervals[-1] if intervals else {}

    return {
        "current_power_w": power,
        "battery": {
            "profile": battery.get("usage"),
            "backup_reserve_pct": battery.get("backupReserve"),
            "storm_guard": battery.get("stormGuard"),
            "charge_from_grid": battery.get("chargeFromGrid"),
        },
        "today": {
            "solar_produced_wh": today.get("energy_produced"),
            "consumed_wh": today.get("energy_consumed"),
            "exported_wh": today.get("energy_exported"),
            "imported_wh": today.get("energy_imported"),
            "battery_charged_wh": today.get("energy_charged"),
            "battery_discharged_wh": today.get("energy_discharged"),
            "battery_soc_pct": today.get("battery_soc") or latest_interval.get("soc"),
        },
    }
