# Project Research Summary

**Project:** Tubtron v2.0 -- Closed-Loop Trust
**Domain:** Closed-loop embedded control for hot tub automation (ESP32/ESPHome + Home Assistant)
**Researched:** 2026-04-12
**Confidence:** HIGH

## Executive Summary

Tubtron v2.0 adds closed-loop reliability to an already-working hot tub TOU automation system. The existing stack (ESP32/ESPHome firmware, Home Assistant on RPi4, AQY212EH photorelays for button injection, 391-test Python decode library) is validated and stays unchanged. The milestone extends it with command-verify-retry feedback, independent power-based heater validation via Enphase, and a reproducible data export pipeline. All new capabilities are additive: they do not redesign what works.

The recommended approach is a strict ESP32/HA responsibility split. Firmware owns sub-second real-time control (button injection, display decode, retry loop). HA owns policy, cross-device correlation, persistence, and alerting. This boundary is non-negotiable: blurring it -- such as having HA automate retries at sub-second granularity or having the ESP32 subscribe to Enphase data -- creates timing and coupling problems that research confirms are worse than the failure modes they solve. The key stack additions are: retry logic in C++ inside `ButtonInjector`, two new ESPHome sensor entities surfacing injection result and attempt count, HA template sensors for power-derived heater state and mismatch detection, and a Python REST API export script. No new infrastructure (no InfluxDB, no MQTT broker, no external DB) is introduced.

The primary risk is the non-idempotent nature of the button-press interface: every retry introduces the possibility of overshoot rather than correction. Research confirms this destroyed the auto-refresh feature in v1. The mitigation is a bounded retry design (max 2 retries, exponential backoff, press-budget enforcement) combined with a hard rule that verification never sends additional presses -- it only reads the display. A secondary risk is automation conflict: TOU and thermal runaway share the same setpoint actuator. Research recommends a graduated thermal runaway response and a "runaway cooldown" flag that TOU checks before acting, preventing the oscillation loop confirmed in production.

## Key Findings

### Recommended Stack

The existing stack requires no changes. Three targeted additions cover all new features. For firmware: retry logic built directly into the `ButtonInjector` state machine using chained `set_timeout` calls (ESPHome `set_retry` was deprecated 2026.2.0 and removed 2026.8.0 -- do not use it). For data: a Python `requests`-based script querying the HA REST API `/api/history/period` endpoint for operational pulls; the existing SCP+SQLite path stays as the fallback for deep historical analysis. For power monitoring: the Enphase Envoy core HA integration (already auto-discovered on LAN) provides `sensor.envoy_<SERIAL>_current_power_consumption`; no custom integration or additional hardware is needed assuming consumption CTs are installed.

**Core technologies:**
- `ButtonInjector` C++ (chained `set_timeout`) -- firmware retry loop -- stays within existing state machine, zero new dependencies, ~224 bytes heap cost
- ESPHome `text_sensor` + `sensor` (2 new entities) -- surface injection result and attempt count to HA -- required for all HA-side reaction logic
- HA template sensors (templates.yaml additions) -- power-derived heater state, mismatch detection, cross-validation -- native HA, no infrastructure added
- `requests` + `pandas` (Python, dev machine) -- REST API export script -- formalizes existing pattern, adds `analysis` dependency group to pyproject.toml
- Enphase Envoy core integration (already present in HA) -- whole-home power as independent heater ground truth -- zero new infrastructure, requires CT clamp hardware validation

**What NOT to add (confirmed):** ESPHome `set_retry` (removed in 2026.8.0), Kalman filter on ESP32 (wrong tool for a decoded digital display), InfluxDB/TimescaleDB (unnecessary infrastructure on RPi4 SD card), MQTT bridge (ESPHome native API covers all needs), `esphome-state-machine` external component (hand-rolled state machine is simpler and already working).

### Expected Features

**Must have (table stakes for unattended operation):**
- Command-verify with bounded retry (ESP32) -- current fire-and-forget causes silent failures; unattended TOU requires automatic recovery
- Command result sensors exposed to HA -- `last_result`, `success_count`, `total_count` as HA entities; prerequisite for all HA-side reaction
- HA-side retry escalation -- if ESP32 exhausts retries, HA alerts and optionally retries once after delay; two-layer defense
- Setpoint drift detection -- compare `detected_setpoint` vs `commanded_setpoint`; alert on mismatch; catches physical button presses and lost-press accumulation

**Should have (differentiators -- add after command path is stable):**
- Enphase power as independent heater ground truth -- cross-validate display-decoded heater state with 4kW power step; catches status bit lies
- Time-series data export script -- REST API pull replacing manual SCP+SQLite; enables systematic thermal model validation
- Command success rate dashboard -- percentage metric with degradation alert; signals wiring wear before failures accumulate

**Defer (v2+):**
- Thermal model seasonal calibration (outdoor temp correlation) -- needs a full season of data; defer to summer/fall 2026
- Dual-source thermal runaway (Enphase + display heater bit) -- defer until power monitoring is validated for several weeks
- Community protocol publication -- high value but orthogonal to closed-loop trust milestone

### Architecture Approach

The architecture is a three-tier pipeline: (1) ESP32 firmware handles all real-time hardware interaction and publishes raw state; (2) HA template sensors and automations perform cross-device correlation and policy; (3) Python scripts on the dev Mac handle batch analysis. New features extend each tier at bounded points without reorganizing the tier boundaries. The key architectural decision -- confirmed by research -- is that retry logic belongs entirely in firmware because it needs sub-100ms timing coupling to the display decode pipeline, while cross-device sensor fusion (heater bit vs. power) belongs entirely in HA because the ESP32 has no access to Enphase data.

**Major components:**
1. `ButtonInjector` (ESP32 C++) -- add `retry_count_`, `max_retries_`, `RETRY_EXHAUSTED` result type; modify `finish_sequence_()` to loop back to PROBING on timeout if retries remain; new `publish_result_()` method
2. HA template sensors (`templates.yaml`) -- layer 1: `binary_sensor.hot_tub_heater_power` (Enphase threshold); layer 2: `binary_sensor.hot_tub_heater_mismatch` (display vs power disagreement >2 min); layer 3: `binary_sensor.hot_tub_display_stale` (data age watchdog)
3. `command_monitor.yaml` (HA automation, new) -- trigger on `injection_result` text sensor state change; alert on retry_exhausted; optional escalation re-attempt
4. `pull_ha_history.py` (Python, dev Mac, new) -- REST API pull of recent entity history; outputs CSV for analysis
5. `analyze_heating.py` (existing, modify) -- add REST API JSON input path alongside existing SQLite path

### Critical Pitfalls

1. **Non-idempotent retry causing setpoint overshoot (Pitfall 5)** -- verification failure can mean "press didn't land" OR "display in mode transition." Retrying on a mode-transition failure causes all retries to land when display normalizes, overshooting the target. Prevention: separate "command failed" from "verify inconclusive." Only retry when display is confirmed in temperature mode. Cap at 2 retries (3 total attempts). Enforce press budget: max N+2 presses for an N-degree delta.

2. **TOU and thermal runaway fighting each other (Pitfall 2)** -- runaway fires, drops setpoint to 80, user re-enables TOU, TOU raises back to 104, runaway fires again. Confirmed in production (4 events in 2 days). Prevention: graduated runaway response (log-only for small overshoot, partial reduction before nuclear floor); `input_boolean.runaway_cooldown` flag that TOU checks before raising setpoint; separate thermal coast-down from actual runaway (extend verify window beyond 5 min).

3. **Heater status bit unreliable as ground truth (Pitfall 3)** -- VS300FL4 heater bit reflects controller intent, not relay state; observed heating at 80F setpoint while bit reports "off." Prevention: use Enphase power and temperature derivative as corroborating signals; never gate safety actions on status bit alone; use 2-of-3 voting (power, bit, temp derivative) for heater-state decisions.

4. **Silent safety automation failure (Pitfall 4)** -- thermal runaway automation works once at deployment, silently breaks months later after HA update or entity rename; user retains false confidence. Prevention: weekly safety heartbeat test validating the trigger chain without executing the action; watchdog automation monitoring runaway enablement state; re-verify after every HA or firmware update.

5. **Stale ESPHome data appearing valid (Pitfall 6)** -- ESP32 disconnects; HA shows last-known value for up to 15 min (API reboot_timeout); template sensors compute with stale data; thermal runaway doesn't fire because stale value is in-range. Prevention: add data-age sensor; reduce API reboot_timeout from 15 to 5 min; add staleness check in safety conditions.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Firmware Retry Loop
**Rationale:** All other features observe or depend on the injection result sensors this phase exposes. Nothing in HA can react to command outcomes until firmware publishes them. This is the single bottleneck dependency for all subsequent phases.
**Delivers:** `ButtonInjector` with bounded retry (max 2, exponential backoff), `RETRY_EXHAUSTED` result type, two new HA entities (`injection_result` text sensor, `injection_attempts` sensor), press-budget enforcement.
**Addresses:** Command-verify bounded retry (table stakes), command result sensors to HA (table stakes).
**Avoids:** Pitfall 1 (net-zero press pairs), Pitfall 5 (retry storm) -- by separating verify-inconclusive from command-failed and enforcing press budget.

### Phase 2: HA Command Monitoring and Escalation
**Rationale:** Depends directly on Phase 1 (requires injection_result sensor). Once firmware publishes results, HA closes the loop with alerting and optional escalation retry.
**Delivers:** `command_monitor.yaml` automation reacting to retry-exhausted events; persistent notification on failure; optional 5-minute-delayed HA-level re-attempt; setpoint drift detection alert comparing commanded vs detected setpoint.
**Addresses:** HA-side retry escalation (table stakes), setpoint drift detection (table stakes).
**Avoids:** Pitfall 11 (new automation behind feature flag for rollback without firmware reflash).

### Phase 3: Enphase Power Validation
**Rationale:** Independent of Phases 1-2 (can be built in parallel), but intentionally deferred until after command path is stable per FEATURES.md. A heater mismatch alert is only actionable when command reliability is proven. Requires identifying actual Enphase entity ID before template sensors can be written.
**Delivers:** `binary_sensor.hot_tub_heater_power` (threshold-based), `binary_sensor.hot_tub_heater_mismatch` (disagree >2 min), `input_number.home_baseline_watts` helper, mismatch alert automation.
**Uses:** Enphase Envoy core HA integration (already present), HA template sensors.
**Avoids:** Pitfall 3 (heater bit lies), Pitfall 7 (power false positives -- mitigated by using power as corroborating signal with 2-of-3 voting, not sole source).

### Phase 4: Data Export Pipeline
**Rationale:** Independent of all firmware changes. Enables systematic validation of Phases 1-3 by making it easy to pull and analyze command success rates, heater correlation, and thermal model accuracy from the dev machine.
**Delivers:** `scripts/pull_ha_history.py` (REST API pull, CSV output); updated `analyze_heating.py` accepting REST API JSON input; `analysis` dependency group in `pyproject.toml`; HA recorder configured for 30-day hot-tub entity retention.
**Uses:** `requests` >=2.32.5, `pandas` >=2.3.0, HA REST API `/api/history/period`.
**Avoids:** Pitfall 8 (DB bloat -- REST API pull adds no recorder writes), Pitfall 12 (DB access friction -- REST API eliminates SQLite file copy for routine checks).

### Phase 5: Observability Dashboard
**Rationale:** After Phases 1-4, all data exists but may not be surfaced clearly. This phase makes system health visible and adds the safety heartbeat test that Pitfall 4 requires.
**Delivers:** Dashboard panel showing command success rate percentage, ESP32 free heap, data age sensor, heater agreement metric; weekly safety heartbeat automation for thermal runaway validation; watchdog automation monitoring runaway enablement state.
**Addresses:** Command success rate dashboard (should-have), Pitfall 4 (silent safety failure), Pitfall 6 (stale data visibility).
**Avoids:** Pitfall 8 (diagnostic sensors excluded from recorder where history is not needed).

### Phase 6: Thermal Runaway Hardening
**Rationale:** The existing thermal runaway automation has a confirmed oscillation problem (Pitfall 2, 4 events in 2 days in production). Defer until Phase 5 provides visibility into actual runaway trigger frequency so graduated thresholds are data-driven, not guessed. This phase modifies working safety logic and requires the most careful testing.
**Delivers:** Graduated runaway response (log-only / partial drop / nuclear floor); `input_boolean.runaway_cooldown` flag wired into TOU automation; extended thermal coast-down tolerance window; automation watchdog as per Phase 5.
**Addresses:** Pitfall 2 (TOU/runaway oscillation), Pitfall 4 (silent safety failure -- watchdog component).
**Avoids:** Disabling safety net under false-positive pressure.

### Phase Ordering Rationale

- Phases 1 and 2 are strictly sequential: HA cannot react to injection outcomes before firmware publishes them.
- Phases 3, 4, and 5 can proceed in parallel after Phase 1 is deployed and soak-tested (48-hour minimum per Pitfall 11 guidance).
- Phase 3 is intentionally placed after command reliability (Phases 1-2): a heater mismatch alert is noise if the command path itself is unreliable.
- Phase 6 is last because it modifies working safety logic; it needs Phase 5's visibility to set graduated thresholds from real data, not assumptions.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (Enphase Power Validation):** Enphase entity ID depends on specific Envoy serial number and CT configuration. Must verify actual entity names in HA Developer Tools before writing template sensors. Also confirm consumption CT clamps are physically installed (production-only installations require CTs; solar-only installations lack them).
- **Phase 6 (Thermal Runaway Hardening):** Optimal graduated response thresholds (2F vs 4F vs 6F, 5 min vs 15 min vs 20 min windows) need real production data to tune. Do not define these values in planning -- measure from Phase 4/5 data first.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Firmware Retry):** Pattern fully specified in STACK.md and ARCHITECTURE.md. C++ changes are bounded and well-understood. No novel patterns.
- **Phase 2 (HA Command Monitoring):** Standard HA state-trigger automation with persistent notification action. No novel patterns.
- **Phase 4 (Data Export):** HA REST API is well-documented; Python pattern is already proven in `analyze_heating.py`.
- **Phase 5 (Observability Dashboard):** Standard HA template sensors and dashboard cards.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All additions verified against official ESPHome and HA docs. `set_retry` deprecation confirmed against official ESPHome developer blog (2026-02-12). Enphase entity patterns from official integration docs. |
| Features | MEDIUM-HIGH | Table stakes features derived from concrete failure modes already observed in production. Differentiators from well-established embedded control patterns. |
| Architecture | HIGH | ESP32/HA responsibility boundary is well-reasoned with specific anti-patterns confirmed by production failures (auto-refresh drift, runaway oscillation). Component-level change list is fully specified. |
| Pitfalls | HIGH | Top pitfalls are documented production failures (auto-refresh drift, runaway oscillation, heater bit unreliability confirmed in STATE.md), not speculative risks. |

**Overall confidence:** HIGH

### Gaps to Address

- **Enphase CT clamp installation:** Research assumes consumption CTs are installed. If they are not, Phase 3 is blocked until hardware is added. Verify before Phase 3 planning begins.
- **Enphase entity ID:** Entity name `sensor.envoy_<SERIAL>_current_power_consumption` requires actual serial number. Check HA Developer Tools > States and search "envoy" before Phase 3 implementation.
- **ESP32 actual free heap:** STACK.md estimates ~100-150KB free; ARCHITECTURE.md cites ~54KB used of 320KB total. These are estimates. Use ESPHome `debug` component to measure actual free heap on the deployed unit before Phase 1 deployment.
- **HA recorder retention policy:** REST API data pull is limited to recorder's `purge_keep_days` window. Confirm current setting and configure to 30 days for hot-tub entities before Phase 4 implementation.
- **Enphase polling frequency:** Official docs state 60-second poll interval. Community reports suggest configurable to 5s via HACS custom integration. For Phase 3 power correlation, the 60-second resolution is likely sufficient (heater cycles are 10-60 minutes); validate before investing in a faster polling setup.
- **Thermal coast-down duration:** How many minutes does water temperature continue rising after the Balboa controller de-energizes the heater? This is the key input for Phase 6 graduated threshold design. Measure via Phase 4 data export before setting thresholds.

## Sources

### Primary (HIGH confidence)
- Home Assistant REST API (developers.home-assistant.io) -- history/period endpoint, auth, params, minimal_response flag
- Enphase Envoy Integration (home-assistant.io/integrations/enphase_envoy) -- entity patterns, CT requirements, firmware versions
- ESPHome Sensor Component (esphome.io/components/sensor) -- filter catalog, binary sensor debounce patterns
- ESPHome `set_retry` Deprecation (developers.esphome.io blog, 2026-02-12) -- deprecated 2026.2.0, removed 2026.8.0
- ESPHome Native API Component (esphome.io/components/api) -- bidirectional push architecture, no MQTT needed
- ESP-IDF Memory Types (docs.espressif.com) -- ESP32 SRAM layout
- Project files: `ha/thermal_runaway.yaml`, `ha/tou_automation.yaml`, `.planning/STATE.md`, `.planning/PROJECT.md` -- confirmed production failures (auto-refresh drift, runaway oscillation, heater bit unreliability)

### Secondary (MEDIUM confidence)
- IEC 61508 Overview and LDRA Guide -- functional safety principles applied as coding discipline
- CNStra Error Handling in State Machines -- bounded retry with exponential backoff pattern
- HA Community: Long-Term Statistics REST API -- confirms REST API limited to short-term recorder window
- Automating a Hot Tub with HA (bentasker.co.uk) -- stale data, overlapping automation conflicts
- HA Community: Appliance Power Monitor Blueprint -- power threshold detection with delay_on/delay_off pattern
- Archimetric: State Machine Diagrams for IoT -- request-response with ACK/NACK/retry

### Tertiary (LOW confidence -- needs validation)
- Enphase polling frequency configurable below 60s (community reports, not in official docs)
- HA REST API hard limit at 10 days (community reports vary 3-10 days depending on recorder config)
- Exact free heap on deployed ESP32 with current firmware (estimated, not measured on device)

---
*Research completed: 2026-04-12*
*Ready for roadmap: yes*
