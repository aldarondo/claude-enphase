# Enphase Solar MCP Server

An MCP (Model Context Protocol) server that exposes tools for monitoring and controlling an Enphase solar + battery system via the Enphase Enlighten web API. Uses stdio transport — Claude Code runs it directly as a subprocess with no HTTP port.

## Prerequisites

- Python 3.11+
- An Enphase Enlighten account with access to your system

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

### Environment variables

| Variable | Description |
|---|---|
| `ENPHASE_EMAIL` | Your Enphase Enlighten login email |
| `ENPHASE_PASSWORD` | Your Enphase Enlighten login password |

`auth.py` calls `load_dotenv()` at import time, so the `.env` file is loaded automatically.

> **Note:** `SITE_ID`, `USER_ID`, and `ENVOY_SERIAL` are currently hardcoded in `api.py`. If your system differs from the defaults (site `3687112`, user `3263059`, envoy `202215001910`), edit those constants directly in `api.py`.

## Running locally (stdio — Claude Code)

Add this server to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "enphase-solar": {
      "command": "python",
      "args": ["/absolute/path/to/claude-enphase/server.py"]
    }
  }
}
```

Claude Code will launch `server.py` as a subprocess over stdio. No HTTP port is used.

## Running tests

```bash
pytest
```

## Available tools

| Tool | Description |
|---|---|
| `enphase_get_status` | Returns current system status: power in Watts, battery state of charge (%), active battery profile, grid status, storm guard state, and today's energy totals. |
| `enphase_set_battery_profile` | Changes the active battery profile. Accepts: `self-consumption`, `cost_savings`, `ai_optimisation`, `backup_only`, `expert`. |
| `enphase_get_energy_summary` | Returns energy production, consumption, import, export, and battery charge/discharge for a given date (or today if omitted). Date format: YYYY-MM-DD. |
| `enphase_get_battery_settings` | Returns full battery configuration: active profile, backup reserve %, charge-from-grid status, storm guard, and other control flags. |
| `enphase_get_savings` | Returns monetary savings breakdown for a date — import cost, export earnings, net cost. Date format: YYYY-MM-DD. Resolution: `DAY` or `MONTH`. |
| `enphase_get_alerts` | Returns any active system alerts or notifications from the Enphase system. |
| `enphase_get_tariff` | Returns the full TOU (time-of-use) rate structure: all rate tiers, their $/kWh prices, and the schedule of which tier is active for each hour of each day of the week, including seasonal and weekend/weekday variations. |

## Weekend auto-scheduler

`server.py` runs a background APScheduler job (America/Phoenix / US/Arizona timezone) that automatically manages the battery profile:

- **Saturday 12:00 AM AZ time** — switches to `self-consumption`
- **Monday 12:00 AM AZ time** — switches back to `cost_savings`

This means the battery optimizes for self-use over the weekend and returns to TOU cost-savings mode on weekdays automatically.
