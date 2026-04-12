---
phase: 05-safety-and-power-validation
plan: 01
subsystem: safety
tags: [home-assistant, yaml, automation, thermal-runaway, tou, input-boolean]

# Dependency graph
requires:
  - phase: 02-architecture-fix-ha-integration
    provides: TOU automation YAML, setpoint entity, thermal runaway YAML
provides:
  - Graduated 3-tier thermal runaway automation (warning/moderate/severe)
  - TOU oscillation prevention via input_boolean.thermal_runaway_active
  - Thermal runaway auto-clear automation for moderate tier
affects: [05-02, 05-03, stale-data-gating, power-validation]

# Tech tracking
tech-stack:
  added: []
  patterns: [choose-block-with-trigger-ids, input-boolean-coordination-flag, reversed-safe-float-defaults]

key-files:
  created:
    - ha/thermal_runaway_clear.yaml
    - tests/test_tou_automation.py
  modified:
    - ha/thermal_runaway.yaml
    - ha/tou_automation.yaml
    - tests/test_thermal_runaway.py

key-decisions:
  - "Warning tier (2-4F) is monitoring-only -- no input_boolean flag set (per D-01 discretion: small overshoots are normal)"
  - "Auto-clear uses reversed safe float defaults: float(999) for temp, float(0) for setpoint in <= comparison"
  - "input_boolean.thermal_runaway_active must be created as HA helper entity manually (not in automation YAML)"

patterns-established:
  - "choose-block dispatch: trigger IDs in triggers, condition: trigger in choose branches, default for lowest tier"
  - "Coordination flag: input_boolean set by safety automation, checked by TOU condition block"
  - "Reversed safe defaults: for <= comparisons use float(999) for value being tested (prevents false clears)"

requirements-completed: [SAFE-01, SAFE-02]

# Metrics
duration: 3min
completed: 2026-04-12
---

# Phase 5 Plan 1: Graduated Thermal Runaway + TOU Oscillation Prevention Summary

**3-tier thermal runaway (warning/moderate/severe) with input_boolean flag coordinating TOU oscillation prevention and auto-clear**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-12T19:47:23Z
- **Completed:** 2026-04-12T19:50:51Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Replaced all-or-nothing thermal runaway with graduated 3-tier response (warning 2-4F, moderate 4-6F, severe >6F)
- Added TOU oscillation prevention: TOU refuses setpoint raises when thermal_runaway_active flag is on
- Created auto-clear automation that clears moderate tier flag when temp returns to setpoint for 2+ minutes
- 66 new/rewritten tests covering all tiers, conditions, cross-checks, and auto-clear behavior
- Full regression suite passes (454 tests)

## Task Commits

Each task was committed atomically:

1. **Task 1: Graduated thermal runaway automation (SAFE-01)**
   - `14047d1` (test) -- failing tests for 3-tier system (43 tests)
   - `a97a5f3` (feat) -- implement graduated thermal_runaway.yaml
2. **Task 2: TOU oscillation prevention + auto-clear (SAFE-02)**
   - `43ecedf` (test) -- failing tests for TOU condition + auto-clear (23 tests)
   - `117afcf` (feat) -- add TOU condition + thermal_runaway_clear.yaml

## Files Created/Modified
- `ha/thermal_runaway.yaml` - Graduated 3-tier thermal runaway automation (replaces old all-or-nothing)
- `ha/thermal_runaway_clear.yaml` - Auto-clear automation for moderate tier flag
- `ha/tou_automation.yaml` - Added input_boolean.thermal_runaway_active condition to block raises during thermal events
- `tests/test_thermal_runaway.py` - 43 tests: structure, trigger tiers, condition gating, severe/moderate/warning responses, cross-checks
- `tests/test_tou_automation.py` - 23 tests: oscillation prevention, TOU structure preserved, cross-check, auto-clear behavior

## Decisions Made
- Warning tier (2-4F) does NOT set input_boolean flag -- monitoring-only per D-01 discretion (small overshoots normal during heating)
- Auto-clear uses reversed safe float defaults: float(999) for temp, float(0) for setpoint prevents false clears on unavailable sensors
- input_boolean.thermal_runaway_active is referenced in YAML but must be created as a HA helper entity by the user

## Deviations from Plan

None - plan executed exactly as written.

## Threat Surface Scan

All threat mitigations from the plan's threat model are implemented:
- T-05-01 (Tampering): Safe float defaults in all triggers -- float(0) temp, float(999) setpoint
- T-05-02 (DoS): input_boolean coordination flag prevents TOU-runaway oscillation
- T-05-03 (Tampering): Auto-clear requires 2-min sustained temp <= setpoint, does NOT re-enable TOU
- T-05-04 (Info Disclosure): ESP32 API status gate in condition block

No new threat surface introduced beyond what was planned.

## Known Stubs

None - all automations are fully wired with real entity references.

## User Setup Required

The following HA helper must be created manually before these automations will work:

- **input_boolean.thermal_runaway_active** -- Create in HA Settings > Devices & Services > Helpers > Toggle. Name: "Thermal Runaway Active". Initial state: off.

## Issues Encountered
None.

## Next Phase Readiness
- Thermal runaway and TOU oscillation prevention are complete
- Ready for 05-02 (stale data gating) which will add ESP32 offline detection automation
- input_boolean.thermal_runaway_active entity must exist in HA before live deployment

## Self-Check: PASSED

- All 6 files exist
- All 4 commits found in history
- All acceptance criteria verified (test classes, trigger IDs, notification IDs, entity references, flag behavior)
- 454 tests pass in full regression suite

---
*Phase: 05-safety-and-power-validation*
*Completed: 2026-04-12*
