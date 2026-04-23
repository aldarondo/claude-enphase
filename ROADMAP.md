# claude-enphase — Roadmap

## Current Milestone
Production deployment — server running reliably on local machine or NAS with Claude Desktop connected

### 🔨 In Progress
[Empty]

### 🟢 Ready (Next Up)

### 📋 Backlog
[Empty]

### 🔴 Blocked
[Empty]

## ✅ Completed
- **Seasonal charge window scheduler + `enphase_set_charge_window` tool (2026-04-21)** — May 1 → noon–3pm (summer, $0.048/kWh), Nov 1 → 10am–3pm (winter, $0.036/kWh); weekend profile scheduler restored alongside it; README fully updated
- **Added `enphase_get_power_flow` tool (2026-04-21)** — solar production W + today's energy balance + live APS TOU rate ($/kWh + tier) + demand charge window status + buyback rate; 14 new tests
- **Added `enphase_check_alerts` tool (2026-04-21)** — combines demand spike risk (low SoC heading into 4–7pm weekday window) and low battery threshold alert; callable by the coordinator on a schedule; 12 new tests
- **Removed weekend auto-scheduler from server.py (2026-04-21)** — profile switching delegated to enphase-juicebox-coordinator; dropped apscheduler/pytz/tzdata deps
- **Enphase + JuiceBox integration deployed (2026-04-18)**
  - `claude-juicebox` (Mosquitto + JuicePassProxy + MCP) live on NAS at port 3001
  - `enphase-juicebox-coordinator` live on NAS at port 8767, daily scheduler at 04:00 AZ
  - Both connected to Claude Desktop via SSE; JuiceBox UDPC redirected and streaming live data
- **Grid charging enabled + backup reserve raised (2026-04-18)**
  - Enabled 2–5am grid charging schedule in Enphase app — prevents repeat of March 17 demand spike
  - Raised backup reserve 10% → 20% for Phoenix monsoon season resilience
- **Full deploy pipeline working end-to-end (2026-04-18)**
  - Fixed `synology deploy` Windows path mangling bug (`fix_nas_path()` + explicit `GIT_SSH_COMMAND` for sudo/root SSH config)
  - Deployed via `synology deploy git@github-claude-enphase:aldarondo/claude-enphase.git /volume1/docker/claude-enphase`
  - Container running at `<YOUR-NAS-IP>:8766`, scheduler confirmed active in logs
- **NAS deployment — persistent Docker container with SSE transport (2026-04-18)**
  - Added SSE transport mode to server.py (`MCP_TRANSPORT=sse` env var; stdio still default for local dev)
  - Added Dockerfile + docker-compose.yml; container runs on NAS at `<YOUR-NAS-IP>:8766`
  - Weekend scheduler (Sat→self-consumption, Mon→cost_savings) now fires reliably 24/7
  - Updated Claude Desktop MCP config to SSE endpoint
  - Fixes: Starlette lifespan API (on_startup removed in 0.40+), tzdata missing in slim image
- **APS bill optimization analysis — 60-day data pull + full report (2026-04-14)**
  - Identified March 17 demand spike root cause: EV charging absorbed all solar, battery starved, $141.60 demand charge
  - Identified consumption doubling from ~73 kWh/day (Feb) to ~150 kWh/day (Mar 17+) — HVAC/AC onset
  - Generated `enphase_60day_data.csv`, `enphase_analysis_report.md`, `enphase_recommendations.md`
  - Projected savings with fixes: ~$70–130/month
- MCP server scaffold with all core tools (status, battery settings, energy summary, savings, tariff, alerts)
- Enphase Enlighten API client with OAuth auth
- APScheduler background job for weekday/weekend battery profile switching (Arizona TOU)
- Full pytest test suite
- `.env.example` credentials template

## 🚫 Blocked

[Empty]
