# Enphase Solar MCP Server

MCP (Model Context Protocol) server for monitoring and controlling an Enphase solar + battery system via the Enphase Enlighten web API. Supports two transport modes:

- **stdio** (default) — Claude Desktop runs it as a local subprocess
- **SSE** — persistent HTTP server; used for NAS/Docker deployment so the background scheduler runs 24/7

## Prerequisites

- Python 3.11+
- An Enphase Enlighten account with access to your system

## Installation

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in credentials
```

### Environment variables

| Variable | Description |
|---|---|
| `ENPHASE_EMAIL` | Your Enphase Enlighten login email |
| `ENPHASE_PASSWORD` | Your Enphase Enlighten login password |
| `MCP_TRANSPORT` | `stdio` (default) or `sse` |
| `MCP_HOST` | SSE bind address (default `0.0.0.0`) |
| `MCP_PORT` | SSE port (default `8766`) |

> **Note:** `SITE_ID`, `USER_ID`, and `ENVOY_SERIAL` are hardcoded in `api.py` (site `3687112`, user `3263059`, envoy `202215001910`). Edit those constants if your system differs.

## Running locally (stdio — Claude Desktop subprocess)

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "enphase": {
      "command": "python",
      "args": ["/absolute/path/to/claude-enphase/server.py"]
    }
  }
}
```

## Running on NAS (SSE — persistent Docker container)

Deployed to a Synology NAS via Docker Compose so the background scheduler runs 24/7 independent of Claude Desktop.

```bash
# Build and start
docker compose up -d --build

# Claude Desktop connects via SSE endpoint
# claude_desktop_config.json:
# "enphase": { "type": "sse", "url": "http://<NAS-IP>:8766/sse" }
```

Deploy from scratch using [claude-synology](https://github.com/aldarondo/claude-synology):

```bash
synology add-deploy-key aldarondo/claude-enphase
synology deploy git@github-claude-enphase:aldarondo/claude-enphase.git /volume1/docker/claude-enphase
synology edit-env /volume1/docker/claude-enphase ENPHASE_EMAIL=you@example.com ENPHASE_PASSWORD=secret
```

## Running tests

```bash
pytest
```

## Available tools

| Tool | Description |
|---|---|
| `enphase_get_status` | Current power (W), battery SoC (%), active profile, grid status, storm guard, today's energy totals |
| `enphase_set_battery_profile` | Change active profile: `self-consumption`, `cost_savings`, `ai_optimisation`, `backup_only`, `expert` |
| `enphase_set_charge_window` | Set the charge-from-grid time window (minutes from midnight). See seasonal schedule below |
| `enphase_get_energy_summary` | Production, consumption, import, export, battery charge/discharge for a date (default today). Format: YYYY-MM-DD |
| `enphase_get_battery_settings` | Full battery config: profile, backup reserve %, charge-from-grid window, storm guard, control flags |
| `enphase_get_savings` | Monetary savings for a date — import cost, export earnings, net cost. Resolution: `DAY` or `MONTH` |
| `enphase_get_power_flow` | Real-time solar production (W), today's energy balance, current APS TOU rate + tier, demand charge window status, and export buyback rate |
| `enphase_check_alerts` | Smart alert evaluation: demand spike risk (low SoC before 4–7pm weekday) and low battery threshold. Designed for coordinator polling |
| `enphase_get_alerts` | Raw active system alerts from the Enphase platform |
| `enphase_get_tariff` | Full APS TOU rate structure: tiers, $/kWh prices, hourly schedule by day and season |

## Background scheduler

`server.py` runs a background APScheduler (US/Arizona timezone) that automatically manages battery profile and charge-from-grid window. In SSE/Docker mode it runs 24/7 independent of any Claude Desktop connection.

### Weekend battery profile

Prevents wasted solar exports on weekends. In `cost_savings` mode the battery has no trigger to discharge on weekends (no demand charge window), so it sits idle while solar exports at $0.085/kWh and the house simultaneously imports from the grid.

| Trigger | Action |
|---|---|
| Saturday 12:00 AM AZ | Switch to `self-consumption` |
| Monday 12:00 AM AZ | Switch back to `cost_savings` |

### Seasonal charge-from-grid window

The charge-from-grid window is optimized per season based on APS R-3 TOU rates and Phoenix solar production patterns.

**Why not 2–5am?** Pre-charging the battery overnight leaves no headroom for morning solar, causing excess solar to export at $0.085/kWh while the house still imports later in the day. Daytime charging lets solar fill the battery first; grid only covers the shortfall.

| Season | Window | Rate | Rationale |
|---|---|---|---|
| Winter (Nov–Apr) — from Nov 1 | 10am–3pm (600–900 min) | $0.036/kWh | Cheapest APS off-peak window; wider buffer for cloudy days when solar is weaker |
| Summer (May–Oct) — from May 1 | Noon–3pm (720–900 min) | $0.048/kWh | Abundant solar handles morning charging; shorter window sufficient; high demand charge ($19.59/kW) makes full battery critical |

The ~20 kWh usable battery capacity (two IQ Battery 10 units, 20% backup reserve) charges at up to ~7.7 kW combined. From 20% to 100% takes ~2.6 hours at full rate, so both windows comfortably cover even cloudy-day worst cases.

### APS demand charge context

Both the battery profile and charge window decisions are driven by APS R-3 demand charge rules:

- **Peak window:** 4–7pm weekdays only
- **Winter demand rate:** $13.75/kW
- **Summer demand rate:** $19.59/kW (42% higher)
- **Billing:** highest 15-min average kW drawn from grid during any peak window in the billing month

The `enphase_check_alerts` tool and `enphase_get_power_flow` tool both surface demand charge context so the coordinator can act before the peak window opens.
