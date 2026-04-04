---
id: T01
parent: S04
milestone: M002
provides: []
requires: []
affects: []
key_files: ["esphome/components/tublemetry_display/button_injector.h", "esphome/components/tublemetry_display/button_injector.cpp", "esphome/components/tublemetry_display/tublemetry_display.h", "esphome/components/tublemetry_display/tublemetry_display.cpp", "tests/test_auto_refresh.py"]
key_decisions: ["loop_refreshing_() reuses presses_remaining_ and adjusting_up_ fields with direction flip after each press release, avoiding new state fields", "known_setpoint_ is never touched in refresh() or loop_refreshing_() — REFRESHING is a display-flash trigger only", "last_setpoint_capture_ms_ uses 0 as sentinel; auto-refresh guard requires > 0 to prevent spurious fires when setpoint is known but timestamp never set"]
patterns_established: []
drill_down_paths: []
observability_surfaces: []
duration: ""
verification_result: "352 pytest tests pass (including 27 new tests in test_auto_refresh.py). ESPHome compile succeeds with [SUCCESS] in 22.21s. test_ladder_capture.py excluded (pre-existing ModuleNotFoundError) and esphome run via project-root venv (consistent with prior milestones)."
completed_at: 2026-04-04T14:25:34.771Z
blocker_discovered: false
---

# T01: Added REFRESHING phase and auto-refresh keepalive: ButtonInjector fires a net-zero down+up sequence every 5 minutes to force the display to flash the setpoint; 352 tests pass and ESPHome compiles clean.

> Added REFRESHING phase and auto-refresh keepalive: ButtonInjector fires a net-zero down+up sequence every 5 minutes to force the display to flash the setpoint; 352 tests pass and ESPHome compiles clean.

## What Happened
---
id: T01
parent: S04
milestone: M002
key_files:
  - esphome/components/tublemetry_display/button_injector.h
  - esphome/components/tublemetry_display/button_injector.cpp
  - esphome/components/tublemetry_display/tublemetry_display.h
  - esphome/components/tublemetry_display/tublemetry_display.cpp
  - tests/test_auto_refresh.py
key_decisions:
  - loop_refreshing_() reuses presses_remaining_ and adjusting_up_ fields with direction flip after each press release, avoiding new state fields
  - known_setpoint_ is never touched in refresh() or loop_refreshing_() — REFRESHING is a display-flash trigger only
  - last_setpoint_capture_ms_ uses 0 as sentinel; auto-refresh guard requires > 0 to prevent spurious fires when setpoint is known but timestamp never set
duration: ""
verification_result: passed
completed_at: 2026-04-04T14:25:34.772Z
blocker_discovered: false
---

# T01: Added REFRESHING phase and auto-refresh keepalive: ButtonInjector fires a net-zero down+up sequence every 5 minutes to force the display to flash the setpoint; 352 tests pass and ESPHome compiles clean.

**Added REFRESHING phase and auto-refresh keepalive: ButtonInjector fires a net-zero down+up sequence every 5 minutes to force the display to flash the setpoint; 352 tests pass and ESPHome compiles clean.**

## What Happened

All four C++ files changed in concert. button_injector.h/cpp got the REFRESHING InjectorPhase enum value, refresh() public method (rejects when busy/unconfigured, sets presses_remaining_=2, adjusting_up_=false, transitions to REFRESHING), and loop_refreshing_() which drives two presses via direction-flip on presses_remaining_ — known_setpoint_ is never touched. tublemetry_display.h got SET_FORCE_INTERVAL_MS=300000 and last_setpoint_capture_ms_ field. tublemetry_display.cpp stamps last_setpoint_capture_ms_ on each confirmed setpoint and adds the auto-refresh guard in loop() that calls refresh() when detected_setpoint_ is NaN or the capture timestamp is > 0 and elapsed >= 300s. tests/test_auto_refresh.py (new, 27 tests) covers both the REFRESHING phase mirror and the auto-refresh trigger logic via Python simulation classes.

## Verification

352 pytest tests pass (including 27 new tests in test_auto_refresh.py). ESPHome compile succeeds with [SUCCESS] in 22.21s. test_ladder_capture.py excluded (pre-existing ModuleNotFoundError) and esphome run via project-root venv (consistent with prior milestones).

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `uv run pytest tests/ --ignore=tests/test_ladder_cache.py --ignore=tests/test_ladder_capture.py -q` | 0 | ✅ pass | 380ms |
| 2 | `/Users/chriskaschner/Documents/GitHub/tubtron/.venv/bin/esphome compile esphome/tublemetry.yaml` | 0 | ✅ pass | 22210ms |


## Deviations

test_ladder_capture.py also needed --ignore (pre-existing issue, not introduced by this task). uv run esphome not found; used /Users/chriskaschner/Documents/GitHub/tubtron/.venv/bin/esphome instead. Two test boundary cases adjusted: confirmation timestamp changed from now_ms=0 to now_ms=1 to avoid the intentional last_setpoint_capture_ms_ > 0 guard — this is correct behavior, not a fix.

## Known Issues

None.

## Files Created/Modified

- `esphome/components/tublemetry_display/button_injector.h`
- `esphome/components/tublemetry_display/button_injector.cpp`
- `esphome/components/tublemetry_display/tublemetry_display.h`
- `esphome/components/tublemetry_display/tublemetry_display.cpp`
- `tests/test_auto_refresh.py`


## Deviations
test_ladder_capture.py also needed --ignore (pre-existing issue, not introduced by this task). uv run esphome not found; used /Users/chriskaschner/Documents/GitHub/tubtron/.venv/bin/esphome instead. Two test boundary cases adjusted: confirmation timestamp changed from now_ms=0 to now_ms=1 to avoid the intentional last_setpoint_capture_ms_ > 0 guard — this is correct behavior, not a fix.

## Known Issues
None.
