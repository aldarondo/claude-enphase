# claude-enphase

## What This Project Is
MCP (Model Context Protocol) server that integrates Claude with an Enphase solar + battery system. Exposes tools for monitoring real-time power status, battery settings, energy summaries, savings breakdowns, TOU tariffs, and alerts. Includes a background scheduler that auto-switches battery profile between self-consumption mode (weekends) and cost-savings mode (weekdays) for Arizona TOU rates.

## Tech Stack
- Python 3.11+
- MCP SDK (Model Context Protocol)
- APScheduler (background battery profile scheduler)
- httpx (async HTTP client for Enphase Enlighten API)
- respx (HTTP mocking for tests)
- pytest
- `.env` for credentials (gitignored)

## Key Decisions
- Credentials stored in `.env` — never committed; see `.env.example`
- Battery scheduling uses Arizona timezone (pytz) — hardcoded for current use case
- MCP server runs as a local process; Claude Desktop connects via stdio transport

## Session Startup Checklist
1. Read ROADMAP.md to find the current active task
2. Check MEMORY.md if it exists — it contains auto-saved learnings from prior sessions
3. Copy `.env.example` → `.env` and fill in Enphase API credentials if missing
4. Run `pip install -r requirements.txt` if dependencies are stale
5. Run `pytest` to verify tests pass before making changes
6. Do not make architectural changes without confirming with Charles first

## Key Files
- `server.py` — MCP server entry point, tool registration
- `api.py` — Enphase Enlighten API client
- `auth.py` — OAuth token management
- `enphase-mcp-plan.md` — original design doc
- `tests/` — pytest test suite
- `.env.example` — credentials template

---
@~/Documents/GitHub/CLAUDE.md

## Git Rules
- Never create pull requests. Push directly to main.
- solo/auto-push OK
