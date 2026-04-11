# Enphase Solar MCP — Implementation Plan

**Site:** ALDARONDO — 15443 N 13th Ave  
**Site ID:** 3687112 | **User ID:** 3263059 | **Envoy Serial:** 202215001910  
**Timezone:** US/Arizona (UTC−7, no DST)  
**Researched:** April 11, 2026

---

## The Problem This Solves

Your TOU tariff has flat/off-peak rates on weekends. This means `cost_savings` mode (and `ai_optimisation`) sees no financial reason to cycle the battery on Saturdays and Sundays — it just lets solar export to the grid cheaply rather than storing it. The battery sits at 10% all weekend while your solar is essentially wasted.

**Data from the weekend of April 4–5, 2026 (forgot to switch manually):**

| Day | Solar Produced | Battery Used | Exported to Grid | Grid Import Cost |
|---|---|---|---|---|
| Fri Apr 3 (weekday, working correctly) | 79.9 kWh | **5.3 kWh** | 33.4 kWh | $5.48 |
| **Sat Apr 4 — stuck in cost_savings ❌** | **81.5 kWh** | **1.6 kWh** | **16.9 kWh** | **$6.46** |
| **Sun Apr 5 — stuck in cost_savings ❌** | **79.0 kWh** | **0.8 kWh** | **22.5 kWh** | **$4.92** |
| Mon Apr 6 (weekday, working correctly) | 37.0 kWh | **8.8 kWh** | 5.0 kWh | $6.30 |

On Saturday with 81.5 kWh of solar, the battery only moved **1.6 kWh** — because `cost_savings` decided weekend rates were too cheap to bother. You paid $6.46 to import grid power while 16.9 kWh of solar went out at low export rates.

**The fix:** Switch to `self-consumption` on weekends so the battery charges from solar first before exporting. Switch back to `cost_savings` (or `ai_optimisation`) on Monday so TOU optimization resumes on weekdays.

Your current manual routine — switch to self-consumption Saturday morning, switch back Sunday night — is correct. This MCP automates it so forgetting is no longer possible.

---

## Recommendation: Build an MCP Server

A **Model Context Protocol (MCP) server** is the right tool. Unlike a one-off script, an MCP exposes tools that Claude can call on demand at any time, plus runs a built-in scheduler for the weekend auto-switch. Once installed, it runs quietly in the background.

---

## The Weekend Schedule

Your timezone is **US/Arizona (UTC−7, no DST — Arizona does not observe Daylight Saving Time)**.

| When | Action | Profile |
|---|---|---|
| **Saturday 12:00 AM** (AZ time = 07:00 UTC) | Switch ON | `self-consumption` |
| **Monday 12:00 AM** (AZ time = 07:00 UTC) | Switch OFF | `cost_savings` |

Switching at midnight Saturday means the battery starts charging from morning solar right away. Switching back at midnight Monday means weekday TOU optimization starts fresh.

Optionally, if you want the Friday night TOU "cheap charging" window to run fully before switching, you could delay the Saturday switch to 6:00 AM instead.

---

## What the Research Found

### Three Available APIs

**1. Enphase Enlighten Internal Web API** ← recommended, full read/write  
Base URL: `https://enlighten.enphaseenergy.com`  
This is what the Enlighten app uses. Confirmed via live session to support reading all data AND writing battery profile changes. Authentication uses email/password login → session cookie + CSRF token.

**2. Official Enphase Developer API v4** ← read-only, cannot change profiles  
Requires OAuth 2.0 registration. Rate-limited. Cannot change battery settings. Only useful if you want official monitoring without credentials.

**3. Local IQ Gateway API** ← on-network only, advanced fallback  
Runs at your Envoy's local IP. Can change some settings without cloud round-trips, but only works when on your home network.

**The MCP uses the Internal Web API (#1).** It's what the app itself uses and has full read/write capability.

---

## Confirmed API Endpoints

### Reading Data

| Endpoint | What It Returns |
|---|---|
| `GET /app-api/3687112/get_latest_power` | Current draw in Watts |
| `GET /pv/systems/3687112/today` | Full day stats: production, consumption, battery SOC, grid flows, 15-min intervals |
| `GET /service/savings/systems/3687112/savings?resolution=DAY&date=YYYY-MM-DD` | Energy and monetary breakdown for any date |
| `GET /service/batteryConfig/api/v1/batterySettings/3687112?source=enho&userId=3263059` | Current profile, backup %, charge schedule, storm guard, all control flags |
| `GET /service/batteryConfig/api/v1/siteSettings/3687112?userId=3263059` | Site config, timezone, feature flags |
| `GET /app-api/3687112/grid_control_check.json` | Grid status |
| `GET /app-api/3687112/new_articles_alert.json` | System alerts and notification flags |
| `GET /app-api/3687112/tariff.json?country=us` | Full TOU rate structure with seasonal/weekend tiers |
| `GET /systems/3687112/weather.json` | Current weather |
| `GET /pv/aws_sigv4/livestream.json?serial_num=202215001910` | AWS IoT credentials for real-time MQTT stream |

### Changing the Battery Profile ⭐

```
POST /service/batteryConfig/api/v1/batterySettings/3687112

Headers:
  Content-Type: application/json
  X-XSRF-Token: {csrf_token}
  Cookie: {session_cookie}

Body (to switch to self-consumption):
{
  "usage": "self-consumption",
  "source": "enho",
  "userId": 3263059
}

Body (to switch back to cost_savings):
{
  "usage": "cost_savings",
  "source": "enho",
  "userId": 3263059
}
```

The OPTIONS preflight on this endpoint confirmed it accepts `GET, POST, PUT` and requires `X-XSRF-Token` in headers. The CSRF token is returned with each session and must be sent on all write requests.

---

## Battery Profiles

| Profile Key | Display Name | Best Used When |
|---|---|---|
| `self-consumption` | Self-Consumption | **Weekends** — charges battery from solar, uses battery before grid |
| `cost_savings` | Cost Savings | **Weekdays** — charges/discharges based on TOU rate schedule |
| `ai_optimisation` | AI Optimization | **Weekdays** — Enphase AI manages automatically (alternative to cost_savings) |
| `backup_only` | Backup Only | Storm prep — keeps battery at 100% |
| `expert` | Expert | Manual schedule control |

**Your current profile:** `self-consumption` (switched manually this morning, April 11)  
**Your backup reserve:** 10%  
**Your tariff type:** TOU with seasonal + weekend rate tiers

---

## Authentication Flow

1. **Login** — `POST https://enlighten.enphaseenergy.com/login/login` with email + password
2. **Session cookie** — stored automatically (`_enlighten_session`)
3. **CSRF token** — fetched from `GET /service/auth_ms_enho/api/v1/session/token`, required on all POST/PUT calls as `X-XSRF-Token` header
4. **Token refresh** — re-authenticate automatically on any 401 response

Credentials stored in a `.env` file as `ENPHASE_EMAIL` and `ENPHASE_PASSWORD`. Never hardcoded.

---

## MCP Tools to Build

**`enphase_get_status`**  
Returns current power (W), battery SOC (%), active profile, grid status, storm guard state, last update time.  
*Example: "What is my system doing right now?"*

**`enphase_set_battery_profile`** ⭐  
Parameters: `profile` — one of `self-consumption`, `cost_savings`, `ai_optimisation`, `backup_only`, `expert`.  
Posts to the batterySettings endpoint to change the active profile.  
*Example: "Switch to self-consumption mode"*

**`enphase_get_energy_summary`**  
Parameters: optional `date` (defaults to today).  
Returns produced, consumed, imported, exported, charged, discharged in kWh. Works for any historical date.  
*Example: "How much solar did I generate last Saturday?"*

**`enphase_get_battery_settings`**  
Returns full battery config: current profile, backup %, charge-from-grid status, storm guard, schedule flags.  
*Example: "What are my current battery settings?"*

**`enphase_get_savings`**  
Parameters: `date`, optional `resolution` (DAY/MONTH).  
Returns monetary savings breakdown — import cost, export earnings, production value.  
*Example: "How much did I spend on electricity this week?"*

**`enphase_get_alerts`**  
Returns alert count and any active system notifications.  
*Example: "Are there any issues with my system?"*

---

## Weekend Auto-Switch — Built Into the MCP

The MCP server runs a background scheduler (using Python's `APScheduler`) so the profile switch happens automatically with zero Claude involvement once deployed.

```python
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

arizona = pytz.timezone('US/Arizona')
scheduler = BackgroundScheduler(timezone=arizona)

# Every Saturday at midnight AZ time: switch to self-consumption
scheduler.add_job(
    lambda: set_profile("self-consumption"),
    'cron', day_of_week='sat', hour=0, minute=0
)

# Every Monday at midnight AZ time: switch back to cost_savings
scheduler.add_job(
    lambda: set_profile("cost_savings"),
    'cron', day_of_week='mon', hour=0, minute=0
)

scheduler.start()
```

If you'd prefer more control, an alternative is using Claude's **schedule skill** to trigger the MCP tools on a cron schedule — same result but Claude is in the loop for each switch.

---

## Project Structure

```
claude-enphase/
├── server.py           # MCP server entry point, tool definitions, scheduler
├── auth.py             # Login, session cookie management, CSRF token refresh
├── api.py              # All API calls (clean wrapper functions)
├── .env                # ENPHASE_EMAIL, ENPHASE_PASSWORD (never committed to git)
├── .env.example        # Template for credentials
├── .gitignore          # Excludes .env
└── requirements.txt    # mcp, httpx, apscheduler, pytz, python-dotenv
```

---

## Build Order

**Phase 1 — Auth + Read Tools** (~1 hour)  
Login flow, session management, `get_status`, `get_energy_summary`, `get_battery_settings`. Verify live data comes back correctly.

**Phase 2 — Profile Change Tool** (~30 min)  
`set_battery_profile`. Test switching to self-consumption and back. Confirm the change shows up in the Enlighten app.

**Phase 3 — Weekend Scheduler** (~30 min)  
Add APScheduler with the Saturday/Monday cron jobs. Test by temporarily setting a 2-minute trigger.

**Phase 4 — Optional Extras** (as desired)  
Savings tracking, alert monitoring, backup % control, real-time MQTT stream.

---

## Security & Rate Limiting Notes

- Store credentials only in `.env`, exclude from git via `.gitignore`
- The XSRF token rotates — always fetch a fresh one before POST/PUT calls
- The Enlighten app polls every 60 seconds; don't poll faster than that
- All API timestamps are UTC — the scheduler converts to US/Arizona internally
- Session cookies expire; the auth module should catch 401s and re-login automatically
