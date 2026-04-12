---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: verifying
stopped_at: Completed 02-03-PLAN.md — all 268 tests passing, phase 02 complete
last_updated: "2026-04-04T00:00:28.713Z"
last_activity: 2026-04-04
progress:
  total_phases: 3
  completed_phases: 2
  total_plans: 6
  completed_plans: 6
  percent: 75
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-13)

**Core value:** The tub automatically lowers its setpoint during on-peak hours and raises it before evening use -- no human involvement required.
**Current focus:** Phase 02 — Architecture Fix + HA Integration

## Current Position

Phase: 02 (Architecture Fix + HA Integration) — EXECUTING
Plan: 3 of 3
Status: Phase complete — ready for verification
Last activity: 2026-04-04

Progress: [███████░░░] 75%

## Performance Metrics

**Velocity:**

- Total plans completed: 3
- Average duration: 5min
- Total execution time: 14min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 3/3 | 14min | 5min |

*Updated after each plan completion*
| Phase 02 P01 | 2min | 2 tasks | 7 files |
| Phase 02 P02 | 2min | 2 tasks | 2 files |
| Phase 02 P03 | 12min | 2 tasks | 5 files |

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
- [Phase 02]: No device_class on temperature sensor — omitting device_class prevents HA unit conversion; unit_of_measurement='degF' is opaque label
- [Phase 02]: number.py uses try/except around injector lookup — injector may not exist in read-only deployments
- [Phase 02]: publish_state() called before request_temperature() in TublemetrySetpoint::control() — optimistic HA update
- [Phase 02]: temperature sensor entry has no entity_category and no device_class to prevent HA unit conversion
- [Phase 02]: tou_automation.yaml uses plain degF integers (104/102/98/96) with number.set_value targeting number.tublemetry_hot_tub_setpoint
- [Phase 02]: number excluded from raw-text YAML check — clock_pin.number sub-key causes false positives; structural parse check is sufficient
- [Phase 02]: test_climate_entity_exists replaced with test_no_climate_entity — guards against accidental re-introduction of removed climate entity
- [Phase 02]: pyyaml added to dev dependencies — was missing, caused import failures in all yaml-based tests

### Pending Todos

None.

### Blockers/Concerns

- Setpoint display frames decoded as current temp (Balboa shows setpoint ~1s after button press -- no way to distinguish from raw 7-seg data). Not blocking for TOU automation.
- ISR can flood WiFi if clock pin gets noise -- pulldowns help. Serial flash required if OTA fails.
- Verification will likely time out (setpoint flash brief and noisy) -- not blocking, setpoint still gets set.

## Session Continuity

Last session: 2026-04-04T00:00:28.710Z
Stopped at: Completed 02-03-PLAN.md — all 268 tests passing, phase 02 complete
Resume file: None
