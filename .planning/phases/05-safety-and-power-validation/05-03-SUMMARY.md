---
phase: 05-safety-and-power-validation
plan: 03
subsystem: power-validation
tags: [home-assistant, yaml, template-binary-sensor, enphase, heater-power, stub]

# Dependency graph
requires:
  - phase: 05-01
    provides: Graduated thermal runaway, TOU oscillation prevention
  - phase: 05-02
    provides: Stale data gating
provides:
  - Enphase-derived heater power binary sensor (stub, ready for wiring)
  - Independent heater state validation separate from display status bit
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: [template-binary-sensor-with-stub-fallback, delay-on-delay-off-debounce]

key-files:
  created:
    - ha/heater_power.yaml
    - tests/test_heater_power.py
  modified: []

decisions:
  - "Stub fallback with {{ false }} -- Enphase CT clamp availability unknown, sensor always reports OFF until user configures entity ID"
  - "Simple threshold approach recommended over derivative -- 60s Enphase update interval too coarse for derivative detection"
  - "delay_off (120s) > delay_on (60s) -- conservative heater-off debounce prevents flickering between poll gaps"

metrics:
  duration: 2min
  completed: 2026-04-12
  tasks_completed: 1
  tasks_total: 2
  status: checkpoint-reached
---

# Phase 05 Plan 03: Enphase Heater Power Detection Summary

Stub template binary sensor for independent heater power validation via Enphase whole-home power consumption, with documented configuration steps for wiring when CT clamps become available.

## What Was Done

### Task 1: Write tests and implement Enphase heater power detection with stub fallback (PWR-01)

**TDD RED phase:** Created `tests/test_heater_power.py` with 12 tests across 4 test classes:
- `TestHeaterPowerYaml` (3 tests): YAML parsing, dict type, template top-level key
- `TestHeaterPowerSensor` (4 tests): binary_sensor list, name "Hot Tub Heater Power", state template, device_class power
- `TestHeaterPowerSafeDefaults` (3 tests): delay_on present, delay_off present, delay_off >= delay_on
- `TestHeaterPowerDocumentation` (2 tests): CONFIGURATION comment, STUB behavior comment

**TDD GREEN phase:** Created `ha/heater_power.yaml` with:
- Template binary sensor named "Hot Tub Heater Power" with unique_id
- Stub state `{{ false }}` (always reports OFF until Enphase entity configured)
- device_class: power, icon: mdi:lightning-bolt
- delay_on: 60 seconds (heater startup debounce)
- delay_off: 120 seconds (poll gap tolerance)
- Detailed comments explaining how to find and configure the Enphase entity ID
- Documentation of stub behavior and independence from safety features (D-14)

### Task 2: Verify complete Phase 5 safety and power validation suite

**Status:** Checkpoint reached. Human verification pending for complete Phase 5 output.

## Commits

| Commit | Type | Description |
|--------|------|-------------|
| 0f5f42a | test | Add failing tests for heater power binary sensor (PWR-01) |
| ca76ee9 | feat | Implement heater power binary sensor with stub fallback (PWR-01) |

## Test Results

- `uv run pytest tests/test_heater_power.py -x`: 12 passed
- `uv run pytest tests/ --ignore=tests/test_ladder_capture.py`: 485 passed

## Deviations from Plan

None -- plan executed exactly as written.

## Known Stubs

| File | Line | Stub | Reason |
|------|------|------|--------|
| ha/heater_power.yaml | 27 | `{{ false }}` -- always reports OFF | Enphase CT clamp availability unknown (per STATE.md blocker). User must configure entity ID per CONFIGURATION comment. Safety features independent per D-14. |

## Decisions Made

1. **Stub over wired sensor:** Enphase CT clamp installation unverified. Created stub that always reports OFF with clear documentation for future wiring. This is intentional per D-13.
2. **Threshold approach documented:** Comments recommend simple >3500W threshold over derivative-based detection due to 60s Enphase polling interval.
3. **Conservative debounce:** delay_off (120s) set higher than delay_on (60s) to prevent false heater-off readings between Enphase poll intervals.

## Self-Check: PASSED

All created files verified on disk. All commit hashes verified in git log.
