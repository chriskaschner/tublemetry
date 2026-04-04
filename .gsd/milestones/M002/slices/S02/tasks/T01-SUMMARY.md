---
id: T01
parent: S02
milestone: M002
provides: []
requires: []
affects: []
key_files: ["esphome/components/tublemetry_display/tublemetry_display.h", "esphome/components/tublemetry_display/tublemetry_display.cpp", "esphome/components/tublemetry_display/button_injector.h"]
key_decisions: ["Kept existing classify_display_state_() structure with no early returns so display_state_sensor_ publish path is always reached", "injector_->feed_display_temperature() still called during set mode to avoid disrupting in-progress PROBING/VERIFYING phases", "Candidate confirmed on second blank frame (not first) — first blank sets mode, second blank confirms setpoint"]
patterns_established: []
drill_down_paths: []
observability_surfaces: []
duration: ""
verification_result: "uv run pytest tests/ --ignore=tests/test_ladder_capture.py -q — 274/274 passed in 0.35s. T02 will add Python mirror tests for the state machine logic."
completed_at: 2026-04-04T13:51:20.172Z
blocker_discovered: false
---

# T01: Added set-mode state machine to classify_display_state_() with blank-frame detection, temperature suppression, setpoint confirmation, and ButtonInjector feedback; 274 existing tests pass

> Added set-mode state machine to classify_display_state_() with blank-frame detection, temperature suppression, setpoint confirmation, and ButtonInjector feedback; 274 existing tests pass

## What Happened
---
id: T01
parent: S02
milestone: M002
key_files:
  - esphome/components/tublemetry_display/tublemetry_display.h
  - esphome/components/tublemetry_display/tublemetry_display.cpp
  - esphome/components/tublemetry_display/button_injector.h
key_decisions:
  - Kept existing classify_display_state_() structure with no early returns so display_state_sensor_ publish path is always reached
  - injector_->feed_display_temperature() still called during set mode to avoid disrupting in-progress PROBING/VERIFYING phases
  - Candidate confirmed on second blank frame (not first) — first blank sets mode, second blank confirms setpoint
duration: ""
verification_result: passed
completed_at: 2026-04-04T13:51:20.173Z
blocker_discovered: false
---

# T01: Added set-mode state machine to classify_display_state_() with blank-frame detection, temperature suppression, setpoint confirmation, and ButtonInjector feedback; 274 existing tests pass

**Added set-mode state machine to classify_display_state_() with blank-frame detection, temperature suppression, setpoint confirmation, and ButtonInjector feedback; 274 existing tests pass**

## What Happened

Added six new members to TublemetryDisplay (SET_MODE_TIMEOUT_MS, in_set_mode_, last_blank_seen_ms_, set_temp_potential_, detected_setpoint_, detected_setpoint_sensor_) plus set_detected_setpoint_sensor() setter. Added set_known_setpoint() to ButtonInjector. Rewrote classify_display_state_() with the set-mode state machine: blank frames set in_set_mode_ and confirm pending candidates; temperature frames during set-mode store a candidate and skip temperature_sensor_ publish; timeout at 2000ms exits set mode. injector_->feed_display_temperature() still called during set mode to keep PROBING/VERIFYING phases functional.

## Verification

uv run pytest tests/ --ignore=tests/test_ladder_capture.py -q — 274/274 passed in 0.35s. T02 will add Python mirror tests for the state machine logic.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `uv run pytest tests/ --ignore=tests/test_ladder_capture.py -q 2>&1 | tail -3` | 0 | ✅ pass | 2400ms |


## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `esphome/components/tublemetry_display/tublemetry_display.h`
- `esphome/components/tublemetry_display/tublemetry_display.cpp`
- `esphome/components/tublemetry_display/button_injector.h`


## Deviations
None.

## Known Issues
None.
