---
id: T02
parent: S02
milestone: M002
provides: []
requires: []
affects: []
key_files: ["tests/test_setpoint_detection.py", "esphome/components/tublemetry_display/sensor.py", "esphome/tublemetry.yaml"]
key_decisions: ["Python SetModeStateMachine mirrors C++ classify_display_state_() exactly, including the suppressed vs temperature event distinction and same-value-no-republish guard", ".venv/bin/esphome does not exist in the worktree — used /Users/chriskaschner/Documents/GitHub/tubtron/.venv/bin/esphome (root project venv)"]
patterns_established: []
drill_down_paths: []
observability_surfaces: []
duration: ""
verification_result: "uv run pytest tests/ --ignore=tests/test_ladder_capture.py -q — 299/299 passed (274 prior + 25 new) in 0.36s. /Users/chriskaschner/Documents/GitHub/tubtron/.venv/bin/esphome compile esphome/tublemetry.yaml — [SUCCESS] Took 25.10 seconds, INFO Successfully compiled program."
completed_at: 2026-04-04T13:54:40.096Z
blocker_discovered: false
---

# T02: Added 25 setpoint-detection tests, wired detected_setpoint in sensor.py and tublemetry.yaml, compiled successfully (299/299 tests pass, [SUCCESS])

> Added 25 setpoint-detection tests, wired detected_setpoint in sensor.py and tublemetry.yaml, compiled successfully (299/299 tests pass, [SUCCESS])

## What Happened
---
id: T02
parent: S02
milestone: M002
key_files:
  - tests/test_setpoint_detection.py
  - esphome/components/tublemetry_display/sensor.py
  - esphome/tublemetry.yaml
key_decisions:
  - Python SetModeStateMachine mirrors C++ classify_display_state_() exactly, including the suppressed vs temperature event distinction and same-value-no-republish guard
  - .venv/bin/esphome does not exist in the worktree — used /Users/chriskaschner/Documents/GitHub/tubtron/.venv/bin/esphome (root project venv)
duration: ""
verification_result: passed
completed_at: 2026-04-04T13:54:40.096Z
blocker_discovered: false
---

# T02: Added 25 setpoint-detection tests, wired detected_setpoint in sensor.py and tublemetry.yaml, compiled successfully (299/299 tests pass, [SUCCESS])

**Added 25 setpoint-detection tests, wired detected_setpoint in sensor.py and tublemetry.yaml, compiled successfully (299/299 tests pass, [SUCCESS])**

## What Happened

Wrote tests/test_setpoint_detection.py with a SetModeStateMachine Python class mirroring the C++ classify_display_state_() state machine. 25 tests across 5 classes cover set-mode entry, timeout, setpoint publish, temperature discrimination, and button injector feed. Updated sensor.py to add CONF_DETECTED_SETPOINT constant, schema entry (mdi:thermometer, STATE_CLASS_MEASUREMENT), and to_code() wiring to parent.set_detected_setpoint_sensor(). Added detected_setpoint sensor entry to esphome/tublemetry.yaml under tublemetry_display sensor block. The root project venv (/Users/chriskaschner/Documents/GitHub/tubtron/.venv/bin/esphome) was used for compilation since .venv/bin/esphome does not exist in the worktree.

## Verification

uv run pytest tests/ --ignore=tests/test_ladder_capture.py -q — 299/299 passed (274 prior + 25 new) in 0.36s. /Users/chriskaschner/Documents/GitHub/tubtron/.venv/bin/esphome compile esphome/tublemetry.yaml — [SUCCESS] Took 25.10 seconds, INFO Successfully compiled program.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `uv run pytest tests/ --ignore=tests/test_ladder_capture.py -q 2>&1 | tail -3` | 0 | ✅ pass | 360ms |
| 2 | `/Users/chriskaschner/Documents/GitHub/tubtron/.venv/bin/esphome compile esphome/tublemetry.yaml 2>&1 | tail -10` | 0 | ✅ pass | 25600ms |


## Deviations

.venv/bin/esphome does not exist in the worktree. Used root project venv at /Users/chriskaschner/Documents/GitHub/tubtron/.venv/bin/esphome instead — same binary, same result.

## Known Issues

None.

## Files Created/Modified

- `tests/test_setpoint_detection.py`
- `esphome/components/tublemetry_display/sensor.py`
- `esphome/tublemetry.yaml`


## Deviations
.venv/bin/esphome does not exist in the worktree. Used root project venv at /Users/chriskaschner/Documents/GitHub/tubtron/.venv/bin/esphome instead — same binary, same result.

## Known Issues
None.
