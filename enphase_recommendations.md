# Enphase APS Bill Optimization — Recommendations
**Generated:** 2026-04-14  
**Current Profile:** `cost_savings` | Reserve: 10% | Charge-from-Grid: Disabled

---

## Priority Order

| # | Action | Monthly Savings | Effort | Risk |
|---|---|---|---|---|
| 1 | Enable grid charging window (2–5am) | ~$80–100 demand charge reduction | Low — toggle in app | None |
| 2 | Raise backup reserve to 20% | $0 savings; improved resilience | Low | Reduces peak shaving by ~10% |
| 3 | Investigate consumption doubling | $50–100 if fixable load found | Medium | None |
| 4 | Switch weekends to `self_consumption` | ~$10–20/month | Medium — requires scheduler | Very low |
| 5 | Consider `ai_optimisation` profile | Unknown; lower certainty | Low | Medium — unknown behavior |

---

## Recommendation 1: Enable Grid Charging — HIGHEST PRIORITY

**What:** Enable the charge-from-grid schedule window (2:00am – 5:00am).  
**Current state:** `chargeFromGrid: false`, `chargeFromGridScheduleEnabled: false`  
**Target state:** Schedule enabled, 2am–5am window, charge target: 80–100%

**Why this is #1:**

The March 17 demand spike cost $141.60 for a single bad hour. It happened because:
- Consumption was so high (~243 kWh) that solar had nothing left over to charge the battery
- With charge-from-grid disabled, the battery sat at 10% reserve all day
- The battery contributed ~1.4 kWh during peak hours instead of the usual ~9–11 kWh

**Had grid charging been enabled**, the battery would have topped up to 80–100% between 2am–5am at ~$0.059/kWh (off-peak rate), and entered the peak window with 10–12 kWh available for discharge. On a day with 243 kWh of consumption, the battery still wouldn't eliminate demand — but it could have shaved the peak by 2–4 kW, reducing the demand charge from $141 to $60–90.

**The math:**
- Grid charging cost: ~12 kWh × $0.059 = $0.71/night
- Monthly grid charging cost: $0.71 × 30 = ~$21/month
- Expected demand charge reduction: $60–100/month
- **Net monthly benefit: ~$40–79/month on demand charges alone**

Note: On days where solar successfully charges the battery (most sunny weekdays before March 17), grid charging runs to top-off only, wasting little energy. On overcast or high-consumption days, it ensures the battery is never caught empty.

**How to enable:**
1. Open Enphase app → Battery → Settings
2. Enable "Charge from grid" 
3. Set schedule: 2:00am – 5:00am
4. Or call: `enphase_set_battery_profile` with updated settings (confirm before executing)

---

## Recommendation 2: Raise Backup Reserve to 20%

**What:** Increase `batteryBackupPercentage` from 10% → 20%  
**Why:**
- Phoenix monsoon season runs July–September with real storm/outage risk
- 10% reserve is the absolute floor — practically useless for backup (estimated ~1 hour at current consumption levels)
- 20% provides a meaningful cushion for weather events without significantly impacting peak shaving

**Tradeoff:** Going from 10% to 20% reserve reduces the battery's usable discharge capacity by roughly 10% of the battery's total capacity. If usable capacity is ~12 kWh, this costs ~1.2 kWh of daily peak shaving — a minor reduction.

**The 10% "very low SoC" floor is already set to 10%** (confirmed in battery settings). Raising reserve to 20% is a net improvement in resilience at minimal cost.

---

## Recommendation 3: Investigate the Consumption Doubling

**What:** Identify why daily consumption jumped from ~73 kWh (Feb–Mar 16) to ~150 kWh (Mar 17+)  
**This is likely HVAC/AC startup**, but the magnitude is worth investigating.

Normal Phoenix spring: AC kicking on adds 2–5 kW of load when running. At 8–10 hours/day operation, that's 16–50 kWh/day — consistent with the observed +75 kWh/day increase.

**If this is normal AC load:** Nothing to do except prepare for higher bills. Focus on Recs 1 and 4.

**If something anomalous is happening:** An HVAC system running continuously (stuck thermostat, refrigerant leak causing inefficiency, compressor short-cycling) could explain 243 kWh on a single day. March 17 is 1.6x higher than even adjacent high-consumption days (Mar 18 = 154 kWh, Mar 20 = 180 kWh). Check:
- HVAC service records around mid-March
- Whether a new appliance was added
- Whether the bakery's electricity is on this same meter

**Impact if a fixable load is found:** Reducing average daily consumption from 150 kWh back toward 100 kWh would cut monthly grid imports by ~1,500 kWh and reduce demand spike risk substantially.

---

## Recommendation 4: Weekday `cost_savings` + Weekend `self_consumption`

**What:** Keep `cost_savings` profile on weekdays (optimal for APS TOU demand charge) but switch to `self_consumption` on weekends (when there is no TOU window and no demand charge exposure).

**Current weekend behavior:**
- Battery charges: ~1,460 Wh (trickle to maintain 10% reserve)
- Battery discharges: ~0–5 Wh
- Solar exported: 30–70% of production at $0.085/kWh
- Grid imported: 20–100 kWh at $0.05–0.10/kWh

**What `self_consumption` would do on weekends:**
- Battery charges from any solar excess above home loads (up to ~12 kWh)
- Battery discharges whenever consumption exceeds solar production (typically evening/night)
- Result: 6–10 kWh of weekend grid imports avoided per day

**Estimated weekend savings:**
- 8–9 weekend days/month × 7 kWh grid imports avoided × $0.07/kWh avg = ~$3.50–4.50/month
- 8–9 weekend days/month × 15 kWh reduced export × ($0.15 − $0.085) = ~$7–9/month
- **Total: ~$10–13/month**

Not transformative, but adds up. The Enphase scheduler in the MCP server already supports profile switching — this can be automated to flip Friday night and restore Monday morning.

---

## Recommendation 5: Consider `ai_optimisation` Profile (Lower Confidence)

**What:** Switch from `cost_savings` to `ai_optimisation`  
**What it claims to do:** Enphase's AI mode forecasts weather, solar production, and consumption to optimize charge/discharge timing including demand management.

**Caution:** The previous battery profile history shows `ai_optimisation` was tried (previous backup percentage set to 10% for it), suggesting it was used and switched away from. The data doesn't reveal why.

**Assessment:** Given the current findings, the specific problem is **not that cost_savings is wrong about timing** — it's that charge-from-grid is disabled and weekends are unoptimized. Fixing those two things within `cost_savings` is a higher-confidence improvement than switching to an AI profile with unknown behavior.

**Revisit if:** After enabling grid charging, if demand spikes persist due to the AI profile failing to pre-charge before high-demand events, then `ai_optimisation` is worth testing.

---

## Behavioral Recommendations

### Don't Run High-Draw Appliances 4–7pm Weekdays
The demand charge is set by the **single highest 60-minute average** during 4–7pm on any weekday in the billing period. One bad hour = $13.75/kW for the entire month.

High-draw offenders to shift outside 4–7pm weekdays:
- Oven/range (3–5 kW)
- Clothes dryer (4–5 kW)
- Dishwasher (1.2–1.8 kW)
- EV charging if applicable (3–7 kW)
- Pool pump if applicable (1–2 kW)

### Pre-Cool the House Before 4pm
If the AC is the major load driver, cooling to 70°F before 4pm and raising the thermostat to 76°F during 4–7pm can reduce HVAC load during peak hours by 1–3 kW. This is especially impactful on extreme heat days when battery alone is insufficient.

### Spring/Summer Threat Calendar
| Month | Risk Level | Notes |
|---|---|---|
| April | High | AC running, consumption ~150 kWh/day |
| May | Very High | Heat rising, potential 190+ kWh/day |
| June | Critical | Peak heat, AC working hardest |
| July–Sept | Critical + Monsoon | Demand spikes + outage risk |
| Oct–Nov | Moderate | AC tapering off |

**Action for May 1:** Confirm grid charging is enabled before the billing period starts. One demand spike in May at $13.75/kW could negate all other optimizations.

---

## Projected Monthly Savings (if Recs 1–4 implemented)

| Improvement | Monthly Savings |
|---|---|
| Grid charging (demand reduction) | $60–100 |
| Grid charging (net of ~$21 charging cost) | −$21 |
| Weekends self-consumption | $10–13 |
| No-load discipline 4–7pm (behavioral) | $20–40 |
| **Total projected savings** | **$69–132/month** |
| Current March bill | $321.58 |
| **Projected bill with improvements** | **~$190–253** |

> Caveat: Demand charge savings depend heavily on whether another spike event occurs. If consumption stays elevated (~150 kWh/day) AND a high-load event hits 4–7pm, demand charge risk remains. Grid charging reduces but does not eliminate this risk.

---

## Immediate Action Checklist

- [ ] **TODAY:** Enable grid charging schedule (2am–5am) in Enphase app before next billing period starts (Apr 7+)
- [ ] **THIS WEEK:** Raise backup reserve from 10% → 20%
- [ ] **THIS WEEK:** Audit March 17 consumption — was this HVAC startup, or something that recurs?
- [ ] **BEFORE MAY BILLING PERIOD:** Implement 4–7pm behavioral load shifting
- [ ] **OPTIONAL:** Set up automated weekend `self_consumption` profile switch in the MCP scheduler
- [ ] **BEFORE MONSOON SEASON (July):** Confirm 20% reserve is in place for outage resilience

---

## Settings Change Summary

| Setting | Current | Recommended |
|---|---|---|
| `profile` | `cost_savings` | Keep `cost_savings` (weekdays) |
| `batteryBackupPercentage` | 10% | **20%** |
| `chargeFromGrid` | false | **true** (scheduled) |
| `chargeFromGridScheduleEnabled` | false | **true** |
| `chargeBeginTime` | 120 min (2am) | Keep 2am |
| `chargeEndTime` | 300 min (5am) | Keep 5am |

> These changes can be applied via `enphase_set_battery_profile` in the MCP server. Confirm before executing.
