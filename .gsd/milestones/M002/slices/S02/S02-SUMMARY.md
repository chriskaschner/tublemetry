---
id: S02
parent: M002
milestone: M002
provides:
  - detected_setpoint_ field on TublemetryDisplay — confirmed setpoint value, NaN until first set-mode sequence completes
  - detected_setpoint HA sensor (sensor.tublemetry_hot_tub_detected_setpoint) — live setpoint from display flash detection
  - set_known_setpoint(float) on ButtonInjector — feeds known setpoint to skip PROBING on next request_temperature() call
  - Set-mode state machine in classify_display_state_() — reusable pattern for S04 auto-refresh (check known_setpoint_ for NaN to decide whether to trigger)
requires:
  []
affects:
  - S04 — auto-refresh keepalive reads known_setpoint_ (NaN = refresh needed) and uses set_known_setpoint() to populate after forced press
key_files:
  - esphome/components/tublemetry_display/tublemetry_display.h
  - esphome/components/tublemetry_display/tublemetry_display.cpp
  - esphome/components/tublemetry_display/button_injector.h
  - esphome/components/tublemetry_display/sensor.py
  - esphome/tublemetry.yaml
  - tests/test_setpoint_detection.py
key_decisions:
  - No early returns in classify_display_state_() — conditional guard wraps temperature_sensor_->publish_state() only, display_state_sensor_ always updated (D003)
  - injector_->feed_display_temperature() still called during set mode to avoid disrupting in-progress PROBING/VERIFYING (D004)
  - Second blank confirms setpoint (not first blank) — first blank only enters set mode and records timestamp (D005)
  - Python mirror test pattern: SetModeStateMachine class with now_ms injection — deterministic, fast, zero hardware dependencies
patterns_established:
  - Python mirror test pattern: implement a Python class that mirrors C++ state machine logic with injectable clock (now_ms parameter). No mocking needed — pure function calls. Reference: tests/test_setpoint_detection.py SetModeStateMachine.
  - Conditional-guard suppression pattern: rather than early returns or flag variables, wrap only the publish call in `if (!in_set_mode_) { ... }`. State variable and state-sensor publish remain unconditional.
observability_surfaces:
  - ESP_LOGI: 'Setpoint detected: %.0fF' — fires when setpoint is confirmed (visible at INFO log level)
  - ESP_LOGD: 'Set mode entry (blank frame)' — fires on each blank frame that enters/maintains set mode
  - ESP_LOGD: 'Set mode candidate: %.0fF (suppressing temperature publish)' — fires on each suppressed temperature
  - ESP_LOGD: 'Set mode timeout — returning to normal' — fires when 2000ms elapses without a blank frame
drill_down_paths:
  - milestones/M002/slices/S02/tasks/T01-SUMMARY.md
  - milestones/M002/slices/S02/tasks/T02-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-04-04T13:58:36.078Z
blocker_discovered: false
---

# S02: Setpoint Detection + Temperature Discrimination

**Added set-mode state machine to classify_display_state_() that detects blank-frame alternation, suppresses temperature publishes during setpoint flashes, exposes a dedicated detected-setpoint HA sensor, and feeds the known setpoint to ButtonInjector so PROBING is skipped.**

## What Happened

S02 delivered display intelligence: the firmware can now tell the difference between a real water temperature and a setpoint flash sequence.

**T01 — C++ state machine (tublemetry_display.cpp/h, button_injector.h)**

The state machine lives inside classify_display_state_(), which is called once per stable decoded frame. Five fields were added to tublemetry_display.h: `in_set_mode_`, `last_blank_seen_ms_`, `set_temp_potential_`, `detected_setpoint_`, and `detected_setpoint_sensor_`. A public `set_detected_setpoint_sensor(sensor::Sensor *)` setter connects the ESPHome sensor object. ButtonInjector gained a `set_known_setpoint(float)` method to receive the confirmed setpoint.

State machine logic:
- **Blank frame**: enters set mode, records timestamp, checks if a candidate exists from the prior frame. If a candidate exists and differs from the last published setpoint, it confirms the setpoint, publishes to detected_setpoint_sensor_, calls injector_->set_known_setpoint(), logs at INFO level, and clears the candidate.
- **Temperature frame during set mode**: timeout check first — if 2000ms has elapsed since the last blank, exits set mode and publishes normally. If still in set mode, stores the value as set_temp_potential_ and skips temperature_sensor_->publish_state(). feed_display_temperature() is still called so any in-progress PROBING/VERIFYING sequences aren't disrupted.
- **Temperature frame outside set mode**: normal path, publishes to temperature_sensor_ immediately.

Key structural decision: no early returns were added to classify_display_state_(). The display_state_sensor_ publish at the end of the function is always reached, so HA's display_state entity accurately reflects the physical display state ("temperature", "blank", etc.) even when the temperature value is suppressed.

All 274 pre-existing tests continued to pass after the C++ changes — the Python test suite doesn't mock classify_display_state_() directly, so this was a clean pass confirming no regressions in the decode pipeline or button injection logic.

**T02 — Tests, sensor wiring, YAML, and compile**

25 new tests in tests/test_setpoint_detection.py cover the state machine via a Python `SetModeStateMachine` mirror class with `now_ms` parameter injection for deterministic timing. Test classes: TestSetModeEntry (6 tests), TestSetModeTimeout (5 tests), TestSetpointPublish (5 tests), TestTemperatureDiscrimination (4 tests), TestButtonInjectorFeed (5 tests).

sensor.py wired the detected_setpoint sensor: CONF_DETECTED_SETPOINT constant, optional schema entry with mdi:thermometer icon and accuracy_decimals=0, and a to_code() handler that calls parent.set_detected_setpoint_sensor(). tublemetry.yaml gained the detected_setpoint sensor block under the tublemetry_display sensor section.

Final state: 299/299 pytest pass (0.44s), firmware compiles [SUCCESS] with 51.3% flash / 11.4% RAM unchanged from S01 baseline.

## Verification

299/299 pytest pass (uv run pytest tests/ --ignore=tests/test_ladder_capture.py -q). ESPHome compile: [SUCCESS], RAM 11.4%, Flash 51.3%, no errors or warnings. Both verified in the worktree at /Users/chriskaschner/Documents/GitHub/tubtron/.gsd/worktrees/M002.

## Requirements Advanced

- R003 — classify_display_state_() suppresses temperature_sensor_->publish_state() during set-mode blank-frame alternation. Verified by 4 TestTemperatureDiscrimination tests + 299/299 pytest pass.
- R004 — detected_setpoint_ field and detected_setpoint_sensor_ wired through sensor.py and tublemetry.yaml. Sensor publishes on setpoint confirmation via blank-temp-blank sequence. 5 TestSetpointPublish tests verify publication logic.
- R009 — set_known_setpoint(float) added to ButtonInjector; called by classify_display_state_() on setpoint confirmation. ButtonInjector known_setpoint_ is populated from display state machine, enabling PROBING skip on next request_temperature() call.

## Requirements Validated

- R003 — TestTemperatureDiscrimination: test_temperature_during_set_mode_is_suppressed confirms published_temperature remains None when in set mode; test_temperature_after_timeout_publishes_normally confirms publish resumes after 2000ms. 299/299 pytest pass. Firmware compiles [SUCCESS].
- R004 — TestSetpointPublish: test_blank_temp_blank_publishes_setpoint confirms setpoint published after blank→temp→blank sequence; test_same_value_not_republished confirms no duplicate publishes. sensor.py wires set_detected_setpoint_sensor(); tublemetry.yaml exposes entity. Compile [SUCCESS].
- R009 — TestButtonInjectorFeed: test_known_setpoint_fed_on_confirmation and test_known_setpoint_fed_with_correct_value verify set_known_setpoint() called with correct value on confirmation. ButtonInjector.known_setpoint_ field is NaN at boot, populated on first detected setpoint.

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

None. Both tasks delivered exactly as planned. The concrete restructure approach (local suppress flag) was considered but the simpler conditional guard approach was used instead — functionally equivalent, slightly less code.

## Known Limitations

Setpoint detection is not verified against live VS300FL4 wire data in this slice — only the Python mirror tests confirm the logic. Live verification happens when the firmware is OTA-flashed to tublemetry.local (R011). The detected_setpoint sensor will show NaN until the controller enters set mode at least once after boot.

## Follow-ups

S04 (auto-refresh keepalive) depends on this slice's set_known_setpoint() path. When known_setpoint_ is NaN (first boot, cache miss), ButtonInjector will still fall back to PROBING — S04 covers keeping the cache warm via periodic COOL press. S03 (status bit binary sensors) is independent of this slice and can proceed immediately.

## Files Created/Modified

- `esphome/components/tublemetry_display/tublemetry_display.h` — Added 5 set-mode state fields (in_set_mode_, last_blank_seen_ms_, set_temp_potential_, detected_setpoint_, detected_setpoint_sensor_), SET_MODE_TIMEOUT_MS constant, set_detected_setpoint_sensor() public setter
- `esphome/components/tublemetry_display/tublemetry_display.cpp` — Added #include <cmath>; restructured blank and is_numeric branches of classify_display_state_() to implement set-mode state machine with suppression, candidate tracking, and setpoint confirmation
- `esphome/components/tublemetry_display/button_injector.h` — Added set_known_setpoint(float) public method and known_setpoint_ float field (NAN default)
- `esphome/components/tublemetry_display/sensor.py` — Added CONF_DETECTED_SETPOINT constant, optional detected_setpoint sensor schema entry, to_code() handler calling set_detected_setpoint_sensor()
- `esphome/tublemetry.yaml` — Added detected_setpoint sensor block under sensor > tublemetry_display with name 'Hot Tub Detected Setpoint'
- `tests/test_setpoint_detection.py` — New file: 25 tests across 5 classes covering set-mode entry, timeout, setpoint publish, temperature discrimination, and ButtonInjector feed via SetModeStateMachine Python mirror class
