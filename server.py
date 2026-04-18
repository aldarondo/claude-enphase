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
from datetime import date

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
        name="enphase_get_alerts",
        description="Returns any active system alerts or notifications from the Enphase system.",
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

        elif name == "enphase_get_battery_settings":
            result = await api.get_battery_settings()

        elif name == "enphase_get_savings":
            target_date = arguments["date"]
            resolution = arguments.get("resolution", "DAY")
            result = await api.get_savings(target_date, resolution)

        elif name == "enphase_get_alerts":
            result = await api.get_alerts()

        elif name == "enphase_get_tariff":
            result = await api.get_tariff()

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return [TextContent(type="text", text=f"Error: {exc}")]


# ---------------------------------------------------------------------------
# Weekend auto-scheduler
# ---------------------------------------------------------------------------

async def _switch_to_self_consumption():
    logger.info("Scheduler: switching to self-consumption (weekend)")
    try:
        await api.set_battery_profile("self-consumption")
        logger.info("Scheduler: switched to self-consumption successfully")
    except Exception:
        logger.exception("Scheduler: failed to switch to self-consumption")


async def _switch_to_cost_savings():
    logger.info("Scheduler: switching to cost_savings (weekday)")
    try:
        await api.set_battery_profile("cost_savings")
        logger.info("Scheduler: switched to cost_savings successfully")
    except Exception:
        logger.exception("Scheduler: failed to switch to cost_savings")


def _build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=ARIZONA)

    # Saturday 12:00 AM AZ time → self-consumption
    scheduler.add_job(
        _switch_to_self_consumption,
        "cron",
        day_of_week="sat",
        hour=0,
        minute=0,
        id="weekend_on",
    )

    # Monday 12:00 AM AZ time → cost_savings
    scheduler.add_job(
        _switch_to_cost_savings,
        "cron",
        day_of_week="mon",
        hour=0,
        minute=0,
        id="weekend_off",
    )

    return scheduler


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _start_scheduler() -> AsyncIOScheduler:
    scheduler = _build_scheduler()
    scheduler.start()
    logger.info("Weekend scheduler started (US/Arizona timezone)")
    logger.info("  Saturday 00:00 AZ → self-consumption")
    logger.info("  Monday   00:00 AZ → cost_savings")
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

    starlette_app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse_transport.handle_post_message),
        ],
        on_startup=[lambda: _start_scheduler()],
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
