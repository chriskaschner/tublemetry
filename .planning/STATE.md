---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 06 complete -- all 3 plans done, HA recovered and running with packages
last_updated: "2026-04-13T03:00:00.000Z"
last_activity: 2026-04-13 -- Phase 06 complete, HA deployed with Git Pull add-on
progress:
  total_phases: 4
  completed_phases: 3
  total_plans: 9
  completed_plans: 9
  percent: 90
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-13)

**Core value:** The tub automatically lowers its setpoint during on-peak hours and raises it before evening use -- no human involvement required.
**Current focus:** Phase 06 complete. Phase 3 (Community Contribution) remaining.

## Current Position

Phase: 06 (ha-deployment-pipeline) -- COMPLETE
Plan: 3 of 3
Status: All plans executed, HA deployed
Last activity: 2026-04-13 -- Phase 06 complete

Progress: [█████████░] 90%

## Performance Metrics

**Velocity:**

- Total plans completed: 9
- Average duration: 5min
- Total execution time: ~30min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 3/3 | 14min | 5min |
| 02 | 3/3 | 16min | 5min |
| 06 | 3/3 | ~15min | 5min |

## Accumulated Context

### Decisions

- [Roadmap revision]: Reversed phase order -- display reading first, button injection second.
- [01-01]: 0x73="9" on VS300FL4 (NOT 0x7B as GS510SZ -- no bottom segment d).
- [01-01]: Dp bit (bit 7) masked before lookup.
- [01-01]: Dumb decoder principle: DisplayState reports display content faithfully, zero business logic on firmware side.
- [01-02]: Frame boundary detection uses micros() gap > 500us. Min pulse 10us for noise rejection.
- [01-02]: ESPHome compile verified -- deprecated APIs fixed (CLIMATE_SCHEMA, ClimateTraits, platform/board).
- [01-02]: Timestamp sensor uses millis() uptime.
- [Hardware validation 2026-03-26]: GPIO18=temp_down, GPIO19=temp_up (swapped from original wiring assumption -- confirmed via test press).
- [Hardware validation 2026-03-26]: 0x34="1" in setpoint display mode (Balboa briefly shows setpoint after button press using different segment pattern for "1").
- [Hardware validation 2026-03-26]: Partial frames dropped silently (unknown bytes -> LOGV, early return if any '?' digit).
- [Hardware validation 2026-03-26]: Confidence sensor publish-on-change only (last_confidence_ tracking added).
- [Hardware validation 2026-03-26]: TEST_PRESS phase added for single raw press (bypasses re-home, for hardware debug).
- [Hardware validation 2026-03-26]: Restart/SafeMode buttons moved to entity_category=diagnostic in HA.
- [2026-03-27]: press_once() must invalidate known_setpoint_ -- test presses change real setpoint without updating cache.
- [2026-03-27]: timeout/abort also invalidate known_setpoint_ -- setpoint location uncertain after failed sequence.
- [2026-03-27]: probe+cache over always-rehome -- user preference: delta presses only (e.g. 10 up for 94->104 vs 49 for re-home).
- [Phase 02]: No device_class on temperature sensor -- omitting device_class prevents HA unit conversion; unit_of_measurement='degF' is opaque label
- [Phase 02]: number.py uses try/except around injector lookup -- injector may not exist in read-only deployments
- [Phase 02]: publish_state() called before request_temperature() in TublemetrySetpoint::control() -- optimistic HA update
- [Phase 02]: temperature sensor entry has no entity_category and no device_class to prevent HA unit conversion
- [Phase 02]: tou_automation.yaml uses plain degF integers (104/102/98/96) with number.set_value targeting number.tublemetry_hot_tub_setpoint
- [Phase 02]: number excluded from raw-text YAML check -- clock_pin.number sub-key causes false positives; structural parse check is sufficient
- [Phase 02]: test_climate_entity_exists replaced with test_no_climate_entity -- guards against accidental re-introduction of removed climate entity
- [Phase 02]: pyyaml added to dev dependencies -- was missing, caused import failures in all yaml-based tests
- [Phase 06]: Git Pull add-on syncs entire repo to /config -- YAML files must be in packages/ subdirectory to land at /config/packages/
- [Phase 06]: Git Pull add-on first run CLEARS /config and restores non-YAML files only -- configuration.yaml, automations.yaml, scripts.yaml, scenes.yaml get wiped
- [Phase 06]: tublemetry-ha repo structure: packages/ subdirectory contains all YAML files, README.md at root
- [Phase 06]: heating_tracker.yaml deprecated (comment-only) -- references removed climate.hot_tub entity
- [Phase 06]: dashboard.yaml excluded from packages -- Lovelace cannot be deployed via HA packages

### Pending Todos

None.

### Blockers/Concerns

- Setpoint display frames decoded as current temp (Balboa shows setpoint ~1s after button press -- no way to distinguish from raw 7-seg data). Not blocking for TOU automation.
- ISR can flood WiFi if clock pin gets noise -- pulldowns help. Serial flash required if OTA fails.
- HA .storage/ was wiped by Git Pull add-on first run (2026-04-13). Integrations re-added manually. History DB survived.

## Session Continuity

Last session: 2026-04-13T03:00:00.000Z
Stopped at: Phase 06 complete. HA recovered, ESPHome reconnected, dashboard created. Phase 3 (Community Contribution) next.
Resume file: None
