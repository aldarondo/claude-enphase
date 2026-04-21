"""
Enphase Solar MCP Server

Exposes tools for monitoring and controlling the Enphase solar + battery system
at site 3687112 (ALDARONDO — 15443 N 13th Ave).

Also runs a background scheduler that automatically switches battery profiles
on weekends (self-consumption) and restores weekday mode (cost_savings) on Monday.

Transport modes:
  stdio (default)  — Claude Desktop spawns this process directly (local dev)
  sse              — Persistent HTTP server; set MCP_TRANSPORT=sse and MCP_PORT=8766
"""

import asyncio
import logging
import os
from datetime import date, datetime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

import api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("enphase-mcp")

ARIZONA = pytz.timezone("US/Arizona")

app = Server("enphase-solar")

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    Tool(
        name="enphase_get_status",
        description=(
            "Returns current system status: power in Watts, battery state of charge (%), "
            "active battery profile, grid status, storm guard state, and today's energy totals."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="enphase_set_battery_profile",
        description=(
            "Changes the active battery profile. "
            "Use 'self-consumption' on weekends, 'cost_savings' or 'ai_optimisation' on weekdays, "
            "'backup_only' before storms, 'expert' for manual schedule control."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "profile": {
                    "type": "string",
                    "enum": ["self-consumption", "cost_savings", "ai_optimisation", "backup_only", "expert"],
                    "description": "The battery profile to activate.",
                }
            },
            "required": ["profile"],
        },
    ),
    Tool(
        name="enphase_get_energy_summary",
        description=(
            "Returns energy production, consumption, import, export, and battery charge/discharge "
            "for a given date (or today if omitted). Date format: YYYY-MM-DD."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format. Defaults to today.",
                }
            },
            "required": [],
        },
    ),
    Tool(
        name="enphase_get_battery_settings",
        description=(
            "Returns full battery configuration: active profile, backup reserve %, "
            "charge-from-grid status, storm guard, and other control flags."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="enphase_get_savings",
        description=(
            "Returns monetary savings breakdown for a date — import cost, export earnings, "
            "net cost. Date format: YYYY-MM-DD. Resolution: DAY or MONTH."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format.",
                },
                "resolution": {
                    "type": "string",
                    "enum": ["DAY", "MONTH"],
                    "description": "Time resolution. Defaults to DAY.",
                },
            },
            "required": ["date"],
        },
    ),
    Tool(
        name="enphase_get_weather",
        description="Returns current weather data from the Enphase system (temperature, conditions, cloud cover if available).",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="enphase_get_alerts",
        description="Returns any active system alerts or notifications from the Enphase system.",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="enphase_check_alerts",
        description=(
            "Evaluates current system conditions and returns active smart alerts. "
            "Checks: (1) demand spike risk — battery SoC below threshold heading into the "
            "4–7pm peak demand window on weekdays; (2) low battery — SoC below a configurable "
            "threshold at any time. Returns a list of alerts with type, severity, message, "
            "and recommended action. Call on a schedule from the coordinator."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "low_soc_threshold": {
                    "type": "number",
                    "description": "SoC % below which to trigger a low-battery alert. Default: 20.",
                },
                "demand_window_soc_threshold": {
                    "type": "number",
                    "description": (
                        "SoC % below which to trigger a demand-spike warning when approaching "
                        "the 4–7pm weekday peak window. Default: 30."
                    ),
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="enphase_set_charge_window",
        description=(
            "Sets the charge-from-grid time window. Times are minutes from midnight (AZ time). "
            "Winter (Nov–Apr): begin=600 (10am), end=900 (3pm) — cheapest off-peak rate. "
            "Summer (May–Oct): begin=720 (noon), end=900 (3pm) — solar handles morning charging. "
            "The background scheduler applies these automatically on May 1 and Nov 1."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "begin_minutes": {
                    "type": "integer",
                    "description": "Window start in minutes from midnight. E.g. 600=10am, 720=noon.",
                },
                "end_minutes": {
                    "type": "integer",
                    "description": "Window end in minutes from midnight. E.g. 840=2pm, 900=3pm.",
                },
            },
            "required": ["begin_minutes", "end_minutes"],
        },
    ),
    Tool(
        name="enphase_get_power_flow",
        description=(
            "Returns real-time solar production (W), today's energy balance (produced / consumed / "
            "imported / exported / battery Wh), current APS TOU rate ($/kWh and tier type), "
            "demand charge window status ($13.75–19.59/kW if importing during 4–7pm weekday), "
            "and export buyback rate. Use this for any production-vs-consumption decision."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="enphase_get_tariff",
        description=(
            "Returns the full TOU (time-of-use) rate structure: all rate tiers, their $/kWh prices, "
            "and the schedule of which tier is active for each hour of each day of the week, "
            "including seasonal and weekend/weekday variations. "
            "Use this to determine the cheapest hours to charge the EV or run high-draw appliances."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
]


# ---------------------------------------------------------------------------
# Tariff helpers (pure — no I/O)
# ---------------------------------------------------------------------------

def _in_season(season: dict, month: int) -> bool:
    start, end = int(season["startMonth"]), int(season["endMonth"])
    if start <= end:
        return start <= month <= end
    return month >= start or month <= end  # wraps year-end (e.g. Nov–Apr)


def _find_active_rate(tariff: dict, now_az: datetime) -> dict | None:
    """Return the active purchase rate period for the given time, or None on failure."""
    try:
        aps_dow = now_az.weekday() + 1  # Python 0=Mon → APS 1=Mon; 6=Sun → 7
        minutes = now_az.hour * 60 + now_az.minute
        season = next((s for s in tariff["purchase"]["seasons"] if _in_season(s, now_az.month)), None)
        if not season:
            return None
        day_group = next((d for d in season["days"] if aps_dow in d["days"]), None)
        if not day_group:
            return None
        fallback = None
        for period in day_group["periods"]:
            if period["startTime"] == "":
                fallback = period
                continue
            if int(period["startTime"]) <= minutes <= int(period["endTime"]):
                return {"period_id": period["id"], "type": period["type"],
                        "rate_per_kwh": float(period["rate"]), "season": season["id"]}
        if fallback:
            return {"period_id": fallback["id"], "type": fallback["type"],
                    "rate_per_kwh": float(fallback["rate"]), "season": season["id"]}
    except Exception:
        pass
    return None


def _demand_charge_context(tariff: dict, now_az: datetime) -> dict | None:
    """Return demand charge info and whether the current time is inside the billing window."""
    try:
        aps_dow = now_az.weekday() + 1
        minutes = now_az.hour * 60 + now_az.minute
        for season in tariff["purchase"]["demandCharge"]["demandChargeSeasons"]:
            if not _in_season(season, now_az.month):
                continue
            for day_group in season.get("days", []):
                if aps_dow not in day_group["days"]:
                    continue
                for period in day_group.get("periods", []):
                    start, end = int(period["startTime"]), int(period["endTime"])
                    return {
                        "in_window": start <= minutes <= end,
                        "window": f"{start // 60}:{start % 60:02d}–{(end + 1) // 60}:{(end + 1) % 60:02d}",
                        "rate_per_kw": float(period["rate"]),
                        "season": season["id"],
                    }
    except Exception:
        pass
    return None


def _buyback_rate(tariff: dict) -> float | None:
    """Extract the flat export buyback rate from tariff."""
    try:
        seasons = tariff["buyback"]["seasons"]
        period = seasons[0]["days"][0]["periods"][0]
        return float(period["rate"])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Alert evaluation (pure — no I/O)
# ---------------------------------------------------------------------------

def _evaluate_alerts(
    soc_pct: float | None,
    now_az: datetime,
    *,
    low_soc_threshold: float = 20.0,
    demand_window_soc_threshold: float = 30.0,
) -> list[dict]:
    """Return active alerts given current SoC and local time. No side effects."""
    alerts = []
    is_weekday = now_az.weekday() < 5  # Mon=0 … Sun=6
    approaching_peak = is_weekday and 12 <= now_az.hour < 19  # noon → 7 pm covers lead-up + window

    if soc_pct is not None and approaching_peak and soc_pct < demand_window_soc_threshold:
        alerts.append({
            "type": "demand_spike_risk",
            "severity": "warning",
            "message": (
                f"Battery SoC is {soc_pct}% — below {demand_window_soc_threshold}% "
                "heading into the 4–7pm peak demand window."
            ),
            "soc_pct": soc_pct,
            "recommended_action": "Switch to self-consumption or reduce load before 4pm.",
        })

    if soc_pct is not None and soc_pct < low_soc_threshold:
        alerts.append({
            "type": "low_battery",
            "severity": "critical" if soc_pct < 10 else "warning",
            "message": f"Battery SoC is {soc_pct}% — below the {low_soc_threshold}% threshold.",
            "soc_pct": soc_pct,
            "recommended_action": "Enable charge_from_grid or reduce consumption.",
        })

    return alerts


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    import json

    try:
        if name == "enphase_get_status":
            result = await api.get_status_summary()

        elif name == "enphase_set_battery_profile":
            profile = arguments["profile"]
            result = await api.set_battery_profile(profile)
            result = {"success": True, "profile_set": profile, "response": result}

        elif name == "enphase_get_energy_summary":
            target_date = arguments.get("date") or date.today().isoformat()
            today_stats = await api.get_today_stats() if target_date == date.today().isoformat() else None
            savings = await api.get_savings(target_date)
            result = {
                "date": target_date,
                "savings": savings,
                "today_stats": today_stats,
            }

        elif name == "enphase_set_charge_window":
            begin = int(arguments["begin_minutes"])
            end = int(arguments["end_minutes"])
            result = await api.set_charge_window(begin, end)
            result = {"success": True, "begin_minutes": begin, "end_minutes": end, "response": result}

        elif name == "enphase_get_battery_settings":
            result = await api.get_battery_settings()

        elif name == "enphase_get_savings":
            target_date = arguments["date"]
            resolution = arguments.get("resolution", "DAY")
            result = await api.get_savings(target_date, resolution)

        elif name == "enphase_check_alerts":
            status = await api.get_status_summary()
            soc_pct = status["today"]["battery_soc_pct"]
            now_az = datetime.now(ARIZONA)
            low_thresh = float(arguments.get("low_soc_threshold", 20))
            demand_thresh = float(arguments.get("demand_window_soc_threshold", 30))
            active = _evaluate_alerts(
                soc_pct, now_az,
                low_soc_threshold=low_thresh,
                demand_window_soc_threshold=demand_thresh,
            )
            result = {
                "checked_at": now_az.isoformat(),
                "soc_pct": soc_pct,
                "alert_count": len(active),
                "alerts": active,
            }

        elif name == "enphase_get_weather":
            result = await api.get_weather()

        elif name == "enphase_get_alerts":
            result = await api.get_alerts()

        elif name == "enphase_get_power_flow":
            power_raw, today, tariff = await asyncio.gather(
                api.get_latest_power(),
                api.get_today_stats(),
                api.get_tariff(),
            )
            now_az = datetime.now(ARIZONA)
            intervals = today.get("intervals", [])
            latest_interval = intervals[-1] if intervals else {}
            rate = _find_active_rate(tariff, now_az)
            demand = _demand_charge_context(tariff, now_az)
            export_rate = _buyback_rate(tariff)
            result = {
                "timestamp": now_az.isoformat(),
                "production": {
                    "solar_w": power_raw.get("latest_power", {}).get("value"),
                },
                "today_wh": {
                    "produced": today.get("energy_produced"),
                    "consumed": today.get("energy_consumed"),
                    "imported": today.get("energy_imported"),
                    "exported": today.get("energy_exported"),
                    "battery_charged": today.get("energy_charged"),
                    "battery_discharged": today.get("energy_discharged"),
                    "battery_soc_pct": today.get("battery_soc") or latest_interval.get("soc"),
                },
                "rate": rate,
                "demand_charge": demand,
                "buyback_rate_per_kwh": export_rate,
            }

        elif name == "enphase_get_tariff":
            result = await api.get_tariff()

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return [TextContent(type="text", text=f"Error: {exc}")]


# ---------------------------------------------------------------------------
# Background scheduler — weekend profiles + seasonal charge windows
# ---------------------------------------------------------------------------

# Charge window constants (minutes from midnight, AZ time)
SUMMER_CHARGE_BEGIN = 720   # noon
SUMMER_CHARGE_END   = 900   # 3pm  (solar handles morning; cheapest non-peak rate)
WINTER_CHARGE_BEGIN = 600   # 10am
WINTER_CHARGE_END   = 900   # 3pm  (off-peak $0.036/kWh window; wider buffer for cloudy days)


async def _switch_to_self_consumption():
    logger.info("Scheduler: switching to self-consumption (weekend)")
    try:
        await api.set_battery_profile("self-consumption")
        logger.info("Scheduler: switched to self-consumption OK")
    except Exception:
        logger.exception("Scheduler: failed to switch to self-consumption")


async def _switch_to_cost_savings():
    logger.info("Scheduler: switching to cost_savings (weekday)")
    try:
        await api.set_battery_profile("cost_savings")
        logger.info("Scheduler: switched to cost_savings OK")
    except Exception:
        logger.exception("Scheduler: failed to switch to cost_savings")


async def _apply_summer_charge_window():
    logger.info("Scheduler: applying summer charge window (%d–%d min)", SUMMER_CHARGE_BEGIN, SUMMER_CHARGE_END)
    try:
        await api.set_charge_window(SUMMER_CHARGE_BEGIN, SUMMER_CHARGE_END)
        logger.info("Scheduler: summer charge window applied OK")
    except Exception:
        logger.exception("Scheduler: failed to apply summer charge window")


async def _apply_winter_charge_window():
    logger.info("Scheduler: applying winter charge window (%d–%d min)", WINTER_CHARGE_BEGIN, WINTER_CHARGE_END)
    try:
        await api.set_charge_window(WINTER_CHARGE_BEGIN, WINTER_CHARGE_END)
        logger.info("Scheduler: winter charge window applied OK")
    except Exception:
        logger.exception("Scheduler: failed to apply winter charge window")


def _build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=ARIZONA)

    # Weekend battery profile switching
    scheduler.add_job(_switch_to_self_consumption, "cron",
                      day_of_week="sat", hour=0, minute=0, id="weekend_on")
    scheduler.add_job(_switch_to_cost_savings, "cron",
                      day_of_week="mon", hour=0, minute=0, id="weekend_off")

    # Seasonal charge-from-grid window transitions
    # Summer (May–Oct): noon–3pm — solar handles morning, grid tops off if needed
    scheduler.add_job(_apply_summer_charge_window, "cron",
                      month=5, day=1, hour=0, minute=0, id="charge_window_summer")
    # Winter (Nov–Apr): 10am–3pm — wider window for cloudy days, cheapest off-peak rate
    scheduler.add_job(_apply_winter_charge_window, "cron",
                      month=11, day=1, hour=0, minute=0, id="charge_window_winter")

    return scheduler


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _start_scheduler() -> AsyncIOScheduler:
    scheduler = _build_scheduler()
    scheduler.start()
    logger.info("Scheduler started (US/Arizona timezone)")
    logger.info("  Sat 00:00 AZ  → self-consumption profile")
    logger.info("  Mon 00:00 AZ  → cost_savings profile")
    logger.info("  May  1 00:00 AZ → summer charge window (%d–%d min)", SUMMER_CHARGE_BEGIN, SUMMER_CHARGE_END)
    logger.info("  Nov  1 00:00 AZ → winter charge window (%d–%d min)", WINTER_CHARGE_BEGIN, WINTER_CHARGE_END)
    return scheduler


async def _run_stdio():
    """Run server with stdio transport (local dev / Claude Desktop subprocess)."""
    scheduler = _start_scheduler()
    try:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())
    finally:
        scheduler.shutdown()


def _run_sse(host: str, port: int):
    """Run server with SSE transport (persistent NAS deployment)."""
    from contextlib import asynccontextmanager
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route
    import uvicorn

    sse_transport = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await app.run(streams[0], streams[1], app.create_initialization_options())

    @asynccontextmanager
    async def lifespan(app):
        scheduler = _start_scheduler()
        yield
        scheduler.shutdown()

    starlette_app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse_transport.handle_post_message),
        ],
        lifespan=lifespan,
    )

    logger.info("Starting SSE server on %s:%d", host, port)
    logger.info("  Claude Desktop endpoint: http://%s:%d/sse", host, port)
    uvicorn.run(starlette_app, host=host, port=port)


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    if transport == "sse":
        host = os.environ.get("MCP_HOST", "0.0.0.0")
        port = int(os.environ.get("MCP_PORT", "8766"))
        _run_sse(host, port)
    else:
        asyncio.run(_run_stdio())
