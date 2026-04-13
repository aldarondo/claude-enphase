# claude-enphase — Roadmap

## Current Milestone
Production deployment — server running reliably on local machine or NAS with Claude Desktop connected

### 🔨 In Progress
[Empty]

### 🟢 Ready (Next Up)
- Deploy server to Synology NAS as a persistent background process (Docker or systemd)
- Verify Claude Desktop MCP config points to the deployed server

### 📋 Backlog
- Add tool: real-time production vs consumption comparison
- Add tool: historical energy data query (7-day, 30-day)
- Add alerting webhook or notification when battery drops below threshold
- Harden scheduler — add logging and failure alerting for profile switch failures
- Write deployment runbook (Docker Compose on NAS)

### 🔴 Blocked
[Empty]

## ✅ Completed
- MCP server scaffold with all core tools (status, battery settings, energy summary, savings, tariff, alerts)
- Enphase Enlighten API client with OAuth auth
- APScheduler background job for weekday/weekend battery profile switching (Arizona TOU)
- Full pytest test suite
- `.env.example` credentials template
