# Domain Pitfalls

**Domain:** Closed-loop reliability, data pipelines, and safety for embedded home automation (hot tub heater control)
**Researched:** 2026-04-12
**System:** Tubtron -- Balboa VS300FL4, ESP32/ESPHome, Home Assistant, 4kW/240V heater on ~300 gal hot tub

---

## Critical Pitfalls

Mistakes that cause rework, unsafe conditions, or loss of trust in the system.

### Pitfall 1: The Auto-Refresh Trap -- "Net-Zero" Operations That Aren't Net-Zero

**What goes wrong:** You design an operation that _should_ be neutral -- press Down then Up, or Up then Down -- to keep the display alive or verify responsiveness. On an unreliable command channel (button presses that require 2-3 attempts to register), one half of the pair gets lost. The operation that was supposed to be net-zero silently becomes a +1 or -1. Over hours and days, setpoint drifts cumulatively in one direction.

**Why it happens:** The fundamental error is treating a non-idempotent toggle channel as if it were idempotent. Each button press is a _relative_ mutation (increment/decrement), not an _absolute_ state-set. When the channel is lossy, relative operations accumulate errors. A pair of relative operations (down+up) only cancels out if both sides land -- which cannot be guaranteed on a channel where individual presses already fail 30-50% of the time.

**Consequences:** In this project, the auto-refresh keepalive was sending down+up press pairs every 5 minutes. Lost presses caused the setpoint to drift by several degrees over hours. On a 4kW heater controlling 300 gallons of water, even a 2-degree upward drift means the heater runs an extra ~40 minutes per cycle, wasting energy and potentially approaching scalding temperatures. This was bad enough that the feature had to be entirely removed.

**Prevention:**
1. Never send "net-zero" pairs of relative operations on a lossy channel. If verification is needed, _read_ the display -- don't poke it.
2. All setpoint commands must be _verify after write_ -- read the display value after pressing, and only consider the command successful if the readback matches the intended target.
3. Design commands as absolute-target operations internally ("set to 104") even though the physical interface is relative (press Up N times). The internal state machine should track "current" vs "target" and only issue presses to close the gap, never speculative "maintenance" presses.
4. If a verification read fails after a command, the correct response is to re-read (not re-press), since the press may have landed but the read was noisy.

**Detection:** Monitor `setpoint` history for slow monotonic drift that doesn't correlate with TOU schedule events. If the setpoint is changing outside of TOU trigger times, something is issuing unsolicited presses.

**This project's lesson (confirmed):** Auto-refresh was removed in v2.0 pre-work. The root cause was exactly this: asymmetric loss rates on the two press directions made "net-zero" operations net-positive or net-negative over time.

---

### Pitfall 2: Automation Fighting Automation -- The TOU/Runaway Oscillation Loop

**What goes wrong:** Two automations with opposing goals act on the same actuator without coordination. In this system: TOU automation raises setpoint to 104 at 7pm. Thermal runaway detects overshoot (e.g., water at 107 due to a transient read or slow heater shutoff), drops setpoint to 80, and disables TOU. Next day, user re-enables TOU, which raises back to 104, runaway fires again because the heater is still running from the previous cycle. The user gets 4 runaway alerts in 2 days and loses trust in both automations.

**Why it happens:**
- The runaway automation's only response is a nuclear option (drop to 80, disable TOU). There is no graduated response.
- TOU automation has no awareness of whether runaway has recently fired, or why TOU was disabled.
- The +2F/5min threshold is tight enough that normal thermal lag (heater off but water still rising from residual heat in the element and plumbing) can trigger it legitimately.
- Re-enabling TOU is a manual action with no "cooldown awareness" -- the system doesn't know whether the root cause was resolved.

**Consequences:** User disables thermal runaway protection ("too many false alarms"), removing the only automated safety net. Or user stops re-enabling TOU, defeating the entire purpose of the system. Either outcome is a loss.

**Prevention:**
1. Implement graduated response in thermal runaway: Level 1 (overshoot 2-3F for 5 min) = log + notify only. Level 2 (overshoot 4F+ or 2F+ for 15 min) = drop setpoint by 5 degrees, not to floor. Level 3 (overshoot 6F+ or sustained 20+ min) = nuclear drop to 80, disable TOU.
2. Add a "runaway cooldown" `input_boolean` that TOU checks before raising setpoint. If runaway fired in the last 2 hours, TOU skips the raise and logs why.
3. Separate "heater overshoot" (expected for 2-5 min after heater cycles off due to thermal mass) from "thermal runaway" (sustained, indicates actual fault). The current 5-minute window may be too short for normal thermal coast-down.
4. Add a "last runaway timestamp" and "runaway count in 24h" sensor. If count > 2 in 24h, escalate to persistent notification requiring manual acknowledgment, not just re-enable.
5. Consider: if thermal runaway detects genuine overshoot, the correct first action might be "hold setpoint where it is" (stop TOU from raising), not "drop to floor" (which creates a huge delta for the next cycle).

**Detection:** Count `thermal_runaway` trigger events per day. More than 1 in 48 hours strongly suggests either a false-positive threshold or an automation-vs-automation loop. Check logs for "TOU re-enabled" events within 4 hours of runaway events.

**This project's lesson (confirmed):** Thermal runaway fired 4 times in 2 days. Some were real (airlock causing overheating), but the response pattern -- nuclear drop, manual re-enable, immediate TOU re-raise -- created a sawtoooth that felt like a loop.

---

### Pitfall 3: Trusting the Heater Status Bit When It Lies

**What goes wrong:** The VS300FL4 reports a heater status bit via the display protocol. Code trusts this bit as ground truth for "is the heater on?" But observation shows water temperature rising while the heater bit reads "off." If safety logic or thermal model calculations depend on this bit, they will make wrong decisions: thermal model computes wrong heating rate (thinks heater is off during heating), safety logic doesn't detect actual heating events, and power consumption estimates are garbage.

**Why it happens:** The heater status bit likely reflects the _controller's intent_ (whether it's calling for heat), not the physical state of the heater relay. With thermal lag, relay bounce, or timing misalignment between the display refresh cycle and the relay driver, the bit can be stale or semantically different from what it appears to mean. On a VS-series controller where all protocol knowledge is reverse-engineered, the exact semantics of each bit are uncertain.

**Consequences:**
- Cooling rate calculation in `sensors.yaml` uses heater "off" windows. If heater is actually on during some "off" windows, cooling rate is underestimated (calculated windows include some heating, showing less cooling than reality).
- Heating rate calculation could similarly be corrupted if a heating event starts before the bit flips.
- Thermal runaway detection relies on temperature vs. setpoint, not heater state directly, so it's partially insulated -- but adding heater-state-aware logic later would introduce this vulnerability.
- Any "heater runtime" tracking for energy cost estimation would be wrong.

**Prevention:**
1. Use Enphase power monitoring as independent ground truth for heater state. A 4kW load appearing/disappearing in whole-house consumption is unambiguous (with caveats -- see Pitfall 7).
2. If using the heater status bit at all, cross-validate: if power monitoring says 4kW draw and heater bit says "off," trust power monitoring. Log the discrepancy.
3. For thermal model calculations, prefer temperature-derivative-based detection over status-bit-based detection. If water temp is rising at >0.1F/min, heating is likely happening regardless of what the bit says.
4. Never gate safety actions on the heater bit. Thermal runaway should trigger on temperature vs. setpoint, not on "heater says it's on and temp is rising."

**Detection:** Compare heater bit transitions with Enphase power spikes. If heater bit ON/OFF transitions don't correlate >90% with 4kW power steps within a 60-second window, the bit is unreliable.

**This project's lesson (confirmed):** User observed heating at 80F setpoint with heater status reporting "off." Documented in STATE.md as a known concern.

---

### Pitfall 4: Silent Safety Failure -- The Automation That Never Fires

**What goes wrong:** Thermal runaway protection is deployed, tested once manually, then never fires in production because conditions never arise (the system works correctly). Months later, when a real fault occurs, the automation fails because: HA updated and broke a template syntax, the entity IDs changed during a firmware update, the sensor went unavailable and the condition check filters it out, or the automation was accidentally disabled during dashboard editing.

**Why it happens:** Safety automations are by definition _rarely triggered_. Unlike TOU automation (which fires 6x/day and breaks loudly if misconfigured), thermal runaway may go months without triggering. Without periodic validation, bit rot goes undetected.

**Consequences:** The safety net doesn't exist when needed. User has false confidence that the system is protected. A real thermal runaway event at 3am goes undetected until morning, when water is at 115F+ and potentially dangerous.

**Prevention:**
1. Build a "safety heartbeat" test. Once per week (or configurable), the automation should fire a _test sequence_ that validates the entire chain: template evaluation returns true/false correctly, entity IDs resolve, notification delivery works, but stops short of actually executing the safety action. Log the test result.
2. Add a "days since last runaway check" sensor. If > 14 days, surface a warning on the dashboard.
3. After any HA update, ESPHome firmware update, or entity rename, manually verify thermal runaway fires by temporarily injecting a fake temperature value via Developer Tools.
4. Use the HA automation watchdog pattern: a secondary automation that monitors whether `automation.hot_tub_thermal_runaway_protection` is enabled and alerts if it's been disabled for more than 1 hour. This catches the "accidentally turned off" failure mode.
5. The watchdog itself needs protection -- the watchdog automation should be labeled as `watchdog_protected` and monitored by a separate mechanism (or at minimum, dashboard visibility).

**Detection:** A sensor that tracks `automation.hot_tub_thermal_runaway_protection` state (on/off) with history. Any period where it's off for >1 hour without a corresponding maintenance note is suspicious. Also: if `last_triggered` for the runaway automation is >30 days ago AND the system has been running, that's either good news (no overshoot) or bad news (broken trigger).

---

## Moderate Pitfalls

### Pitfall 5: Retry Storms on a Flaky Actuator

**What goes wrong:** Button press fails (doesn't register on display). Retry logic sends another press. Also fails. Logic sends 3rd, 4th, 5th press. Meanwhile, the display was in a transient state (showing "St" for standby mode instead of temperature), so _verification_ kept failing even though presses were landing. When the display returns to temperature mode, it shows the setpoint has moved +5 from target because all 5 presses actually landed, they just couldn't be verified during the transient.

**Why it happens:** Retry logic assumes that a failed _verification_ means the _command_ didn't land. On this system, verification failure has multiple causes: display in non-temperature mode (mode letters Ec, SL, St), decode confidence drop during frame transitions, WiFi latency delaying the readback, or genuine press failure. Retrying on all of these conflates "command didn't arrive" with "can't confirm command arrived."

**Prevention:**
1. Separate "command failed" from "verification inconclusive." If display is showing mode letters or decode confidence is low, do not retry -- wait for the display to stabilize, then verify.
2. Cap retries strictly: max 2 retries (3 total attempts), with exponential backoff (e.g., 1s, 3s, 10s).
3. After max retries, enter a "degraded" state: log the failure, notify, but do NOT keep pressing. The worst case for a failed setpoint change is "TOU schedule is off by 4 degrees for one cycle." The worst case for a retry storm is "setpoint slammed to 80 or 104 unexpectedly."
4. Track the display state (temperature vs. mode) and only attempt commands when in temperature display mode. Queue commands during mode transitions.
5. Implement a "press budget" per command: for a delta of N degrees, allow at most N+2 presses total (allowing 2 retries for lost presses). If press count exceeds budget, halt and alert.

**Detection:** Track `total_presses_per_command` and `commands_with_retries` counters. If >30% of commands need retries, the press timing parameters need tuning, not more retries.

---

### Pitfall 6: Stale Data Masking Real Problems

**What goes wrong:** ESPHome sensor goes offline (WiFi disconnect, ESP32 reboot, display cable loose). HA continues showing the last known temperature value for minutes to hours. Template sensors derived from this value (preheat ETA, heating rate) keep computing with stale data. TOU automation fires and sets a setpoint based on stale temperature. Thermal runaway sees stale temp and doesn't fire because the stale value is within range, even though actual temperature may have drifted significantly.

**Why it happens:** HA's default behavior for disconnected ESPHome devices is to mark entities as `unavailable`, but this only happens after the API connection timeout (configured at 15 min in tublemetry.yaml). During that 15-minute window, values are stale but appear valid. Additionally, the `heartbeat: 30s` filter on the temperature sensor means even when connected, the value only updates every 30 seconds, which during rapid heating (0.3F/min) means up to 0.15F staleness. The SQL sensors in `sensors.yaml` refresh hourly (`scan_interval: 3600`), meaning heating/cooling rate estimates can be up to 1 hour old.

**Specific risk in this system:** The `hot_tub_preheat_minutes` template uses `sensor.hot_tub_heating_rate` (hourly refresh) and `sensor.tublemetry_hot_tub_temperature` (30s heartbeat). If the heating rate changed due to seasonal temperature shifts, the preheat estimate could be 30-60 minutes wrong until the next SQL refresh.

**Prevention:**
1. Add a `last_update` age check to critical template sensors. If `sensor.tublemetry_hot_tub_temperature` hasn't updated in >5 minutes, treat data as stale and halt automations that depend on it.
2. Reduce the ESPHome API `reboot_timeout` from 15 min to 5 min, so stale-but-appears-valid windows are shorter.
3. Add a dashboard indicator showing "data age" -- the time since last successful display decode. Already partially exists (`sensor.tublemetry_hot_tub_last_update`) but needs to be surfaced prominently.
4. Thermal runaway's condition block already checks for `unknown`/`unavailable`, but needs an additional check: if the temperature value hasn't changed in >10 minutes, treat it as suspect (water temperature in a hot tub with a running heater changes continuously).
5. For SQL sensors, consider reducing `scan_interval` to 1800 (30 min) or triggering a refresh after TOU setpoint changes, since that's when the heating rate estimate matters most.

**Detection:** A sensor that computes `now() - last_update_time` for the temperature entity. Alert if >5 minutes during normal operation.

---

### Pitfall 7: Power Monitoring False Positives from Other 240V Loads

**What goes wrong:** Enphase whole-house power monitoring shows a 4kW spike. System concludes "heater is on." Actually, it's the clothes dryer. Or the EV charger. Or the oven. The system records a phantom heating event, corrupting the thermal model. Or worse: during a real heater-on event, the dryer also runs, showing 8kW total. System concludes "two heaters" or gets confused by the unexpected power level and marks the data as invalid, missing a real heating event.

**Why it happens:** Whole-house power monitoring via CTs at the main panel sees aggregate consumption, not per-circuit. Research on NILM (non-intrusive load monitoring) confirms that purely resistive 240V loads at similar power levels -- like a 4kW heater and a 4-5kW dryer heating element -- are essentially indistinguishable. Enphase does not do load disaggregation; it reports total consumption.

**Consequences:**
- False positive: dryer run mistakenly counted as heater run, corrupting heating rate calculation (thermal model thinks heater ran for 45 minutes but water temp didn't change, computing a heating rate near zero).
- False negative: during concurrent loads, the "4kW step" detection gets confused by the staircase of multiple loads.
- Seasonal variation: baseline consumption changes with HVAC load. A 4kW threshold that works in spring may have too many false positives in winter (electric heating) or summer (AC compressor).

**Prevention:**
1. Do NOT use power as the sole heater-on signal. Use it as a _corroborating_ signal alongside the heater status bit and temperature derivative. If 2 of 3 agree, heater is on. If only power says "on" but temp is flat and heater bit is off, it's probably another appliance.
2. Use time-of-day correlation: dryer runs are clustered during daytime human activity hours. Hot tub heater runs correlate with TOU schedule changes. An EV charger typically runs on a schedule (e.g., overnight). Context narrows the candidates.
3. Use step detection, not threshold detection: look for a ~4kW _increase_ from baseline (not absolute level > 4kW). This survives baseline shifts but still fails on concurrent loads.
4. If the Enphase system supports per-circuit CT monitoring (via IQ Load Controller or additional CTs), use that for the hot tub circuit specifically. This eliminates the disaggregation problem entirely. Investigate whether the hot tub's 240V circuit has a dedicated breaker that could host a CT.
5. Accept that power monitoring will be an _approximate_ signal, not a _definitive_ one. Design the thermal model to tolerate some noise in the heater-on/heater-off signal by using rolling averages and discarding statistical outliers.

**Detection:** Compare power-derived heater events with temperature-derivative-confirmed heater events. If <70% correlation, the power signal has too much noise to be useful as primary input.

---

### Pitfall 8: Overwhelming HA with API Calls / Database Bloat

**What goes wrong:** Adding observability (more sensors, more frequent polling, SQL queries against the recorder DB) degrades HA performance on the RPi4. The `scan_interval: 3600` SQL sensors seem fine, but adding real-time power monitoring, per-command-attempt logging, retry counters, and additional derived sensors creates dozens of new entities that each generate recorder writes. HA SQLite DB grows faster, history graphs slow down, and eventually the RPi4's SD card starts showing I/O latency.

**Why it happens:** Each new sensor added to HA generates at least one state change per update interval. The recorder writes all state changes to SQLite by default. On a Raspberry Pi 4 with SD card storage, write throughput is limited. The current SQL sensors already query the full `states` table with 30-day windows -- adding more sensors increases both write load (more entities) and read load (more SQL queries against a larger DB).

**Prevention:**
1. Be ruthless about recorder exclusion. New diagnostic/debugging sensors should be excluded from the recorder unless they're explicitly needed for history graphs. Use `recorder: exclude: entities:` in HA config.
2. Set `recorder.purge_keep_days` to 10-14 days (not the default, which may be longer). For thermal model queries that look back 30 days, the SQL sensors already handle this window -- you don't need the full recorder to retain 30 days of everything.
3. Prefer event-based logging over high-frequency polling for command attempts. Instead of a sensor that updates every second with retry state, fire an HA event on each command attempt and completion, then use the logbook or a custom counter.
4. Consider moving the HA recorder to MariaDB on the Synology NAS (the user has one) rather than SQLite on the RPi4. This also solves the "DB inaccessible from dev machine" blocker -- MariaDB can be queried remotely.
5. For the thermal model SQL sensors, the 30-day lookback window with correlated subqueries is computationally expensive on SQLite. If these queries start taking >5 seconds, they'll block the HA main thread. Monitor query execution time.

**Detection:** Monitor `homeassistant_v2.db` file size and growth rate. If growing >100MB/week, identify the chattiest entities and exclude them. Monitor HA startup time -- if >2 minutes, the DB is likely too large.

---

### Pitfall 9: Timestamp Misalignment in Data Correlation

**What goes wrong:** Power monitoring data from Enphase, temperature data from ESPHome, and setpoint data from HA entities all have different timestamps, sampling rates, and latency characteristics. When the thermal model tries to correlate "setpoint raised at T=0, temperature reached target at T=45min," the actual timestamps could be off by 30-120 seconds due to:
- ESPHome temperature `heartbeat: 30s` filter (up to 30s lag)
- Enphase cloud API polling interval (typically 15-minute granularity for consumption data)
- HA state change timestamps being "when HA received the update," not "when the physical event happened"
- SQL `last_updated_ts` being the HA-side timestamp, not the ESP32's local clock

**Why it happens:** Each data source has its own clock, sampling rate, and pipeline latency. The `analyze_heating.py` script already resamples everything to a 1-minute grid, which masks small misalignments but can shift event boundaries by up to 1 minute. For heating rate calculations, 1-minute error on a 45-minute event is ~2% error -- acceptable. But for "did the heater turn on within 60 seconds of the setpoint change?" type correlation, misalignment matters.

**Prevention:**
1. Always use HA-side timestamps (`last_updated_ts`) for correlation, not source-side timestamps. This ensures all data is on the same clock even if it's slightly lagged from physical reality.
2. Add tolerance windows to all event correlation. "Heater turned on within 2 minutes of setpoint raise" not "within 30 seconds."
3. For Enphase data specifically: if using the cloud API, expect 5-15 minute granularity. This makes it useless for real-time correlation but fine for "did the heater run for approximately the expected duration today?" type validation.
4. If per-circuit monitoring becomes available, prefer local polling (Envoy local API, ~1 second updates) over cloud API (15-minute updates).
5. Document the expected latency of each data source explicitly, so future correlation logic knows its error budget.

**Detection:** In the thermal model output, check whether heating event "start time" aligns with setpoint change time to within 2 minutes. If events are consistently offset by >5 minutes, a pipeline is adding unexpected latency.

---

## Minor Pitfalls

### Pitfall 10: Over-Engineering Sensor Fusion for a 2-3 Source System

**What goes wrong:** Seeing "sensor fusion" in the milestone goals, the temptation is to build a Kalman filter or Bayesian estimator that fuses temperature, heater bit, and power monitoring into a unified state estimate. This adds significant complexity (matrix math, tuning parameters, initialization) for a system with only 2-3 independent signals. The fusion model becomes the hardest thing to debug when something goes wrong, and its internal state is opaque to dashboard inspection.

**Why it happens:** "Sensor fusion" is a well-established technique in robotics and aerospace, where you have 6+ noisy sensors that need to be combined in real-time. Applying the same approach to a system with a temperature sensor, a maybe-trustworthy status bit, and an aggregate power measurement is overkill. The signals are too few and too different in nature (continuous float, binary bit, aggregate power) to benefit from formal fusion.

**Prevention:**
1. Use simple voting logic instead of formal sensor fusion. "If 2 of 3 sources agree the heater is on, it's on." This is debuggable, dashboardable, and requires no matrix algebra.
2. For the thermal model, use the temperature derivative as the primary signal and the other sources as sanity checks, not inputs to a combined estimator.
3. Reserve complexity for when simple approaches demonstrably fail. If the voting logic gives wrong answers >10% of the time, _then_ consider something more sophisticated.
4. Every derived signal should be independently displayable on the dashboard. If you can't explain what each sensor is contributing by looking at a history graph, the fusion is too opaque.

**Detection:** If debugging a thermal model discrepancy requires reading source code rather than looking at dashboard graphs, the system is too complex for the number of data sources.

---

### Pitfall 11: Breaking Existing Working Features When Adding New Ones

**What goes wrong:** The TOU automation works. Thermal runaway works. Display decoding works. In the process of adding retry logic, the probe+cache setpoint control gets a new code path that subtly changes press timing. Or adding a new sensor entity causes the ESPHome component to use more RAM, making WiFi less stable. Or adding SQL sensors slows HA enough that the API connection to ESPHome times out more often, increasing button press failures.

**Why it happens:** Integration effects. The existing system runs at a specific resource envelope (ESP32 RAM/CPU, WiFi stability, HA responsiveness). New features consume from the same resource pool. ESPHome on ESP32 WROOM-32 has limited RAM (~320KB usable); each new sensor entity consumes some. HA on RPi4 has limited I/O throughput; each new SQL query consumes some.

**Prevention:**
1. Measure baseline before adding features: ESP32 free heap, WiFi reconnect rate, HA response time for API calls, button press success rate. After each new feature, re-measure.
2. Add features one at a time and soak-test for at least 48 hours (covering multiple TOU cycles) before adding the next.
3. If ESP32 free heap drops below 50KB, new entities must be justified. Consider consolidating diagnostic text sensors into fewer entities.
4. If button press success rate drops after a change, back out the change before investigating.
5. Keep a "feature flag" pattern: new features should be disable-able via `input_boolean` helpers without requiring a firmware reflash or HA restart.

**Detection:** Dashboard panel showing ESP32 free heap, WiFi signal, uptime, and button press success rate. Any sustained degradation after a change is a regression signal.

---

### Pitfall 12: HA SQLite DB Inaccessible from Dev Machine

**What goes wrong:** The thermal model validation requires querying `home-assistant_v2.db`, which lives on the RPi4 running HA OS. The dev machine cannot directly access this file. The `analyze_heating.py` script requires a local copy of the DB. Copying a live SQLite DB while HA is writing to it can produce a corrupted copy (SQLite WAL mode). This creates a friction that blocks iteration: every thermal model change requires SSH into the RPi, stop recorder, copy DB, restart, copy to dev machine, test.

**Why it happens:** HA OS runs in a containerized environment on the RPi4. The SQLite DB is in the container's `/config/` directory. Direct file access requires Samba addon, SSH addon, or SCP. The DB is frequently locked by HA's recorder, making live copies risky.

**Prevention:**
1. Set up the Samba or SSH addon on HA OS for dev access.
2. Use `sqlite3 .backup` (not `cp`) to get a consistent copy: `sqlite3 /config/home-assistant_v2.db ".backup /tmp/ha_backup.db"` -- this works even while HA is writing.
3. Better: expose data via HA's REST API or long-lived access tokens. The `analyze_heating.py` script could query the HA API for entity history instead of the DB directly. The `/api/history/period` endpoint returns JSON.
4. Best: migrate the recorder to MariaDB on the Synology NAS. This is network-accessible, supports concurrent reads, and eliminates the SQLite-on-SD-card performance and accessibility concerns simultaneously.
5. For thermal model iteration specifically: export a snapshot CSV of the relevant entity histories once per week, and iterate against the CSV locally. Only go back to the live DB for final validation.

**Detection:** If thermal model changes take >1 hour to validate due to data access friction, the pipeline needs improvement.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Command reliability (retry logic) | Pitfall 5: retry storm overshooting setpoint | Cap retries at 2, separate "command failed" from "verify inconclusive," enforce press budget |
| Command reliability (verify after write) | Pitfall 1 variant: verification read triggers display mode change | Only verify by reading display, never by sending additional presses; wait for stable temperature display mode before verifying |
| Data pipeline (SQL sensors) | Pitfall 8: new sensors bloat DB on RPi4 | Exclude diagnostic sensors from recorder; consider MariaDB migration to Synology |
| Data pipeline (remote access) | Pitfall 12: iteration blocked by DB access | Use HA REST API or MariaDB migration; don't depend on SQLite file copy |
| Power monitoring (Enphase) | Pitfall 7: dryer/oven/EV false positives | Never use power as sole heater signal; use 2-of-3 voting with temp derivative and heater bit |
| Power monitoring (correlation) | Pitfall 9: timestamp misalignment between Enphase and ESPHome | Use HA-side timestamps only; add 2-minute tolerance windows |
| Safety hardening (thermal runaway) | Pitfall 2: TOU and runaway fighting each other | Implement graduated response; add runaway cooldown flag; separate thermal coast from runaway |
| Safety hardening (validation) | Pitfall 4: safety automation silently breaks | Weekly heartbeat test; watchdog automation monitoring runaway enablement state |
| Sensor fusion | Pitfall 10: over-engineering for 2-3 sources | Simple voting logic, not Kalman filter; every signal independently visible on dashboard |
| Integration testing | Pitfall 11: new features degrade existing ones | Measure baseline metrics; 48-hour soak test per feature; feature flags for rollback |
| Heater status trust | Pitfall 3: status bit lies about heater state | Cross-validate with power and temp derivative; never gate safety on status bit alone |
| Stale data | Pitfall 6: stale ESPHome data masks real conditions | Add data-age sensors; reduce API reboot timeout; check staleness in safety conditions |

---

## Summary of Root Causes

The pitfalls in this system cluster around three root causes:

1. **Non-idempotent operations on a lossy channel.** The button-press interface is fundamentally relative and lossy. Every feature that sends presses must account for lost presses and the impossibility of "undoing" a press. This rules out net-zero pairs, makes retry logic dangerous, and forces verify-after-write as the only safe pattern.

2. **Multiple automations sharing a single actuator without coordination.** TOU, thermal runaway, and future retry logic all write to the same setpoint number entity. Without explicit priority ordering and mutual awareness (via shared state like `input_boolean` flags), they will conflict. The solution is a clear hierarchy: safety > manual override > TOU schedule > convenience features.

3. **Insufficient observability creating false confidence.** The system has sensors that _appear_ to work (heater bit, temperature) but may be unreliable in ways that only manifest under specific conditions. Adding more derived sensors (thermal model, power correlation) can amplify this by building on shaky foundations. Every new signal needs its own validation before being trusted as input to decisions.

---

## Sources

- Project files: `ha/thermal_runaway.yaml`, `ha/tou_automation.yaml`, `ha/sensors.yaml`, `ha/thermal_model.yaml`, `esphome/tublemetry.yaml`
- Project state: `.planning/STATE.md` (heater status bit concern, button press reliability, DB access blocker)
- Project decisions: `.planning/PROJECT.md` (auto-refresh removal, thermal runaway deployment)
- [Home Assistant Retry Integration (amitfin/retry)](https://github.com/amitfin/retry) -- exponential backoff patterns and expected_state verification
- [HA Watchdog Rate Limiting Issue](https://community.home-assistant.io/t/configurable-retries-or-exponential-backoff-for-watchdog-to-avoid-rate-limit-exceeded-more-than-10-calls-in-000/896253)
- [Home Assistant Automation Watchdog](https://andrewdoering.org/blog/2025/home-assistant-automation-watchdog/) -- patterns for protecting safety automations from accidental disabling
- [Automating a Hot Tub with Home Assistant (bentasker.co.uk)](https://www.bentasker.co.uk/posts/blog/house-stuff/automating-our-hottub-with-home-assistant.html) -- stale data, deadman switch, overlapping automation conflicts
- [Home Brew Pool Automation](https://www.troublefreepool.com/threads/home-brew-pool-automation-w-arduino-and-home-assistant.322511/) -- failsafe patterns for safety-critical heater control
- [Idempotence on Embedded Systems](https://www.embeddedrelated.com/showarticle/629.php) -- garage door opener analogy for non-idempotent toggle operations
- [NILM Disaggregation Limitations (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC3571813/) -- resistive load confusion
- [PNNL Load Disaggregation Study](https://www.pnnl.gov/main/publications/external/technical_reports/pnnl-24230.pdf) -- systematic mislabeling in every home tested
- [HA SQL Sensor Performance](https://community.home-assistant.io/t/sql-affecting-ha-speed-and-responsiveness/637705)
- [Optimizing HA Database](https://allthingsempty.wordpress.com/2026/02/18/optimising-your-home-assistant-database-without-tears/)
- [HA ESP8266 False Positive Sensor Readings](https://admantium.medium.com/home-assistant-how-to-fix-api-disconnection-and-false-positive-sensor-readings-with-esp8266-boards-c4baa8e0987b) -- sensor reconnection triggering all sensors
- [Stale PZEM Sensor Values](https://community.home-assistant.io/t/pzem-004t-stale-or-unavailable-sensor-values/906907) -- stale data appearing valid
- [Binary Sensor Unknown State After Boot (esphome#10411)](https://github.com/esphome/esphome/issues/10411)

*Pitfalls analysis: 2026-04-12*
