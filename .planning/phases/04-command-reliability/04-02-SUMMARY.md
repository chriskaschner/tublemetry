---
phase: 04-command-reliability
plan: 02
subsystem: firmware, ha-automation
tags: [esphome, codegen, text_sensor, sensor, drift-detection, persistent-notification, template-trigger]

# Dependency graph
requires:
  - phase: 04-01
    provides: "ButtonInjector retry/budget state machine with sensor setter methods"
provides:
  - "Three new HA sensor entities (last_command_result, injection_phase, retry_count) wired through ESPHome codegen"
  - "Injector setpoint_number pointer wired for deferred publish callback"
  - "Drift detection HA automation at ha/drift_detection.yaml"
affects: [05-display-reliability, 06-observability]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Injector sensor registration via try/except for read-only mode graceful degradation", "HA drift detection via template trigger with for: duration and injection_phase idle gate"]

key-files:
  created:
    - ha/drift_detection.yaml
    - tests/test_drift_detection.py
  modified:
    - esphome/components/tublemetry_display/text_sensor.py
    - esphome/components/tublemetry_display/sensor.py
    - esphome/components/tublemetry_display/number.py
    - esphome/tublemetry.yaml

key-decisions:
  - "Injector sensors registered via try/except in text_sensor.py and sensor.py -- graceful degradation in read-only mode"
  - "setpoint_number wired in number.py (not __init__.py) -- keeps injector<->setpoint bidirectional wiring co-located"
  - "Drift detection uses fixed notification_id to overwrite (not duplicate) notifications"

patterns-established:
  - "Injector sensor registration: get injector variable by ID in sensor/text_sensor to_code(), wire via try/except"
  - "HA drift detection: template trigger comparing two entities, gated on third entity state, with for: duration"

requirements-completed: [CMD-01, CMD-02]

# Metrics
duration: 4min
completed: 2026-04-12
---

# Phase 04 Plan 02: Sensor Entity Codegen and Drift Detection Summary

**Three new ESPHome sensor entities (last_command_result, injection_phase, retry_count) wired to ButtonInjector via Python codegen, plus HA drift detection automation comparing detected vs commanded setpoint with 2-minute idle-gated mismatch window**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-12T15:51:27Z
- **Completed:** 2026-04-12T15:55:35Z
- **Tasks:** 2
- **Files modified:** 6 modified, 2 created

## Accomplishments
- Three new sensor entities (last_command_result, injection_phase, retry_count) registered through ESPHome codegen and declared in tublemetry.yaml
- Injector setpoint_number pointer wired in number.py for deferred publish callback (D-14)
- Drift detection automation at ha/drift_detection.yaml with injection_phase idle gate (D-10), 2-minute sustained mismatch (CMD-02), and persistent notification (D-09)
- 14 new drift detection validation tests, 436 total tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Register new sensor entities in Python codegen and YAML** - `03775ae` (feat)
2. **Task 2: Create drift detection automation and validation tests** - `0302d5f` (test, RED) + `e7c685d` (feat, GREEN)

## Files Created/Modified
- `esphome/components/tublemetry_display/text_sensor.py` - Added last_command_result and injection_phase text sensor schemas, injector wiring via try/except
- `esphome/components/tublemetry_display/sensor.py` - Added retry_count sensor schema, injector wiring via try/except
- `esphome/components/tublemetry_display/number.py` - Added injector.set_setpoint_number(var) for deferred publish
- `esphome/tublemetry.yaml` - Declared 3 new sensor entities in text_sensor and sensor platform blocks
- `ha/drift_detection.yaml` - New drift detection HA automation (template trigger, idle gate, persistent notification)
- `tests/test_drift_detection.py` - 14 validation tests across 5 test classes

## Decisions Made
- Injector sensors registered via try/except in text_sensor.py and sensor.py rather than routing through __init__.py -- keeps sensor registration co-located with schema definitions and gracefully handles read-only mode
- setpoint_number wired in number.py right after set_button_injector() -- keeps bidirectional injector<->setpoint wiring co-located rather than splitting across __init__.py
- Drift detection uses fixed notification_id: setpoint_drift so repeated drift events overwrite rather than duplicate notifications (mitigates T-04-06)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- CMD-01 and CMD-02 requirements fully wired: retry/budget logic (Plan 01) + sensor entities and drift detection (Plan 02)
- Injection outcomes now observable in HA via three new sensor entities
- Drift detection automation ready to deploy alongside firmware update
- All 436 tests passing, ready for verification

## Self-Check: PASSED

All 7 files verified present. All 3 commits verified in history.

---
*Phase: 04-command-reliability*
*Completed: 2026-04-12*
