# Enphase Solar MCP Server

MCP (Model Context Protocol) server for monitoring and controlling an Enphase solar + battery system via the Enphase Enlighten web API. Supports two transport modes:

- **stdio** (default) — Claude Code runs it as a local subprocess
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

## Running locally (stdio — Claude Code subprocess)

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

Deployed to a Synology NAS via Docker Compose so the weekend battery scheduler runs 24/7 independent of Claude Desktop.

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
| `enphase_get_energy_summary` | Production, consumption, import, export, battery charge/discharge for a date (default today). Format: YYYY-MM-DD |
| `enphase_get_battery_settings` | Full battery config: profile, backup reserve %, charge-from-grid, storm guard, control flags |
| `enphase_get_savings` | Monetary savings for a date — import cost, export earnings, net cost. Resolution: `DAY` or `MONTH` |
| `enphase_get_alerts` | Active system alerts and notifications |
| `enphase_get_tariff` | Full TOU rate structure: tiers, $/kWh prices, hourly schedule by day/season |

## Weekend auto-scheduler

`server.py` runs a background APScheduler job (US/Arizona timezone) that automatically manages the battery profile:

- **Saturday 12:00 AM AZ** — switches to `self-consumption`
- **Monday 12:00 AM AZ** — switches back to `cost_savings`

When running as a NAS Docker container (SSE mode), the scheduler runs continuously independent of any Claude Desktop connection.
