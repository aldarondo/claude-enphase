# claude-enphase — Roadmap

## Current Milestone
Production deployment — server running reliably on local machine or NAS with Claude Desktop connected

### 🔨 In Progress
- Enphase + JuiceBox integration — solar-aware EV charging (pause during 4–7pm peak, shift to 2–5am off-peak, charge from solar excess only)

### 🟢 Ready (Next Up)
- Enable grid charging schedule (2–5am) in battery settings — immediate action to prevent repeat of March 17 demand spike
- Raise backup reserve from 10% → 20% for Phoenix monsoon season resilience

### 📋 Backlog
- Automated weekend `self_consumption` profile switch (Friday night → Monday morning) via MCP scheduler
- Add demand spike alert — notify when battery SoC is low heading into 4–7pm window on a weekday
- Add tool: real-time production vs consumption comparison
- Add alerting webhook or notification when battery drops below threshold
- Harden scheduler — add logging and failure alerting for profile switch failures
- Write deployment runbook (Docker Compose on NAS)

### 🔴 Blocked
[Empty]

## ✅ Completed
- **Full deploy pipeline working end-to-end (2026-04-18)**
  - Fixed `synology deploy` Windows path mangling bug (`fix_nas_path()` + explicit `GIT_SSH_COMMAND` for sudo/root SSH config)
  - Deployed via `synology deploy git@github-claude-enphase:aldarondo/claude-enphase.git /volume1/docker/claude-enphase`
  - Container running at `192.168.0.64:8766`, scheduler confirmed active in logs
- **NAS deployment — persistent Docker container with SSE transport (2026-04-18)**
  - Added SSE transport mode to server.py (`MCP_TRANSPORT=sse` env var; stdio still default for local dev)
  - Added Dockerfile + docker-compose.yml; container runs on NAS at `192.168.0.64:8766`
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
