"""
Enphase Solar MCP Server

Exposes tools for monitoring and controlling the Enphase solar + battery system
at site 3687112 (ALDARONDO — 15443 N 13th Ave).

Transport modes:
  stdio (default)  — Claude Desktop spawns this process directly (local dev)
  sse              — Persistent HTTP server; set MCP_TRANSPORT=sse and MCP_PORT=8766
"""

import asyncio
import logging
import os
from datetime import date

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

import api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("enphase-mcp")

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
# Entry point
# ---------------------------------------------------------------------------

async def _run_stdio():
    """Run server with stdio transport (local dev / Claude Desktop subprocess)."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


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
        yield

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
