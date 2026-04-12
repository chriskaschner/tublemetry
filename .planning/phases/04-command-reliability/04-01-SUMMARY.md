---
phase: 04-command-reliability
plan: 01
subsystem: firmware
tags: [esphome, state-machine, retry, backoff, button-injection, tdd]

# Dependency graph
requires:
  - phase: 02-architecture-fix-ha-integration
    provides: ButtonInjector state machine, TublemetrySetpoint number entity
provides:
  - RETRYING phase with exponential backoff (5s/15s/45s) in ButtonInjector
  - FAILED and BUDGET_EXCEEDED result types
  - Press budget enforcement (N+2) per attempt
  - Deferred setpoint publish pattern (non-optimistic HA state)
  - New sensor setters for last_command_result, injection_phase, retry_count
affects: [04-command-reliability, drift-detection, ha-entity-registration]

# Tech tracking
tech-stack:
  added: []
  patterns: [retry-with-backoff state machine, deferred-publish pattern, press-budget enforcement]

key-files:
  created: []
  modified:
    - tests/test_button_injection.py
    - esphome/components/tublemetry_display/button_injector.h
    - esphome/components/tublemetry_display/button_injector.cpp
    - esphome/components/tublemetry_display/tublemetry_setpoint.h
    - esphome/components/tublemetry_display/tublemetry_setpoint.cpp

key-decisions:
  - "BUDGET_EXCEEDED as distinct InjectorResult type (not reusing TIMEOUT)"
  - "Backoff table as static const array in calculate_backoff_ms_() (5s/15s/45s)"
  - "Updated existing timeout tests to expect RETRYING instead of COOLDOWN on first timeout"

patterns-established:
  - "Retry state machine: VERIFYING -> attempt_failed_() -> RETRYING -> loop_retrying_() -> PROBING (re-probe from scratch)"
  - "Press budget: N+2 per attempt, budget_exceeded routes through same retry path as timeout"
  - "Deferred publish: TublemetrySetpoint::control() stores pending_target, does NOT publish_state; injector publishes on SUCCESS/FAILED"

requirements-completed: [CMD-01]

# Metrics
duration: 8min
completed: 2026-04-12
---

# Phase 4 Plan 1: Command Reliability Summary

**ButtonInjector retry logic with exponential backoff (5s/15s/45s), press budget enforcement (N+2), and deferred setpoint publish pattern**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-12T15:36:49Z
- **Completed:** 2026-04-12T15:45:06Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Extended SimulatedInjector Python mirror with retry, budget, and deferred-publish behavior; 7 new test classes (31 new tests, 110 total)
- Implemented C++ retry logic: RETRYING phase, attempt_failed_() router, loop_retrying_() with backoff timer, calculate_backoff_ms_() lookup table
- Added press budget enforcement in loop_adjusting_() -- presses_consumed_ tracked per press, budget_exceeded triggers retry path
- Changed TublemetrySetpoint::control() from optimistic publish to deferred pattern: pending_target stored, publish_state only on SUCCESS (or revert on FAILED)
- Added sensor setter infrastructure for last_command_result, injection_phase, retry_count (entity registration deferred to plan 02)

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend SimulatedInjector and write failing tests** - `c6a16a3` (test)
2. **Task 2: Implement C++ retry logic, budget, deferred publish** - `78276a7` (feat)

## Files Created/Modified
- `tests/test_button_injection.py` - Extended SimulatedInjector with retry/budget/deferred-publish state; 7 new test classes covering retry logic, backoff timing, exhaustion, press budget, budget-exceeded retry, result sensors, deferred setpoint
- `esphome/components/tublemetry_display/button_injector.h` - Added RETRYING phase, FAILED/BUDGET_EXCEEDED results, retry/budget/sensor members, new setter methods, loop_retrying_/attempt_failed_/calculate_backoff_ms_ declarations
- `esphome/components/tublemetry_display/button_injector.cpp` - Implemented retry state machine (loop_retrying_, attempt_failed_, calculate_backoff_ms_), budget enforcement in loop_adjusting_, retry-aware finish_sequence_, new sensor publishing in publish_state_
- `esphome/components/tublemetry_display/tublemetry_setpoint.h` - Added pending_target_ and last_confirmed_setpoint_ members
- `esphome/components/tublemetry_display/tublemetry_setpoint.cpp` - Replaced optimistic publish with deferred pattern (D-14): stores pending_target, passes last_confirmed_setpoint to injector, publishes current state on rejection

## Decisions Made
- Used BUDGET_EXCEEDED as a distinct InjectorResult type rather than reusing TIMEOUT -- clearer diagnostics and the plan left this as Claude's discretion
- Updated two existing tests (test_timeout_result, test_next_sequence_after_timeout_probes) to reflect retry-first behavior -- timeout now goes to RETRYING instead of COOLDOWN when retries remain
- Backoff implemented as static const lookup table rather than computed exponential -- matches plan specification exactly (5000, 15000, 45000)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing timeout tests for retry behavior**
- **Found during:** Task 1 (test extension)
- **Issue:** Existing TestStateMachine::test_timeout_result and TestSetpointInvalidation::test_next_sequence_after_timeout_probes expected timeout to go directly to COOLDOWN, but with retry logic, first timeout goes to RETRYING
- **Fix:** Updated test_timeout_result to assert RETRYING phase; updated test_next_sequence_after_timeout_probes to exhaust all retries before checking idle -> probing flow
- **Files modified:** tests/test_button_injection.py
- **Verification:** All 110 tests pass
- **Committed in:** c6a16a3 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Necessary correction -- existing tests had to reflect the new retry-first behavior. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Retry logic and press budget are fully implemented in C++ and tested via Python mirror
- New sensor setters (last_command_result, injection_phase, retry_count) are defined but need entity registration in __init__.py codegen (plan 02)
- Deferred setpoint publish is active -- TOU automation number.set_value calls will wait for injection result
- Drift detection automation (CMD-02) can proceed using the new injection_phase sensor to gate evaluation

---
## Self-Check: PASSED

All 5 modified files verified present. Both task commits (c6a16a3, 78276a7) verified in git log. 422 tests passing.

---
*Phase: 04-command-reliability*
*Completed: 2026-04-12*
