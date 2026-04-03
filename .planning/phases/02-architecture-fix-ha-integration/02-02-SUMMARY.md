---
phase: 02-architecture-fix-ha-integration
plan: 02
subsystem: esphome-yaml + ha-automation
tags: [yaml, esphome, ha-automation, number-entity, tou, degF]
dependency_graph:
  requires: [02-01 — TublemetrySetpoint C++ class + number.py codegen in place]
  provides: [tublemetry.yaml wired with temperature sensor + setpoint number; tou_automation.yaml targeting number entity with degF values]
  affects: [esphome/tublemetry.yaml, ha/tou_automation.yaml]
tech_stack:
  added: []
  patterns: [ESPHome number platform entry, HA number.set_value action]
key_files:
  created: []
  modified:
    - esphome/tublemetry.yaml
    - ha/tou_automation.yaml
decisions:
  - "temperature sensor entry has no entity_category and no device_class — bare name only, per project constraint"
  - "number block placed between sensor and text_sensor blocks — matches YAML reading order and avoids disrupting existing sections"
  - "tou_automation.yaml description TODO comment removed — automation is now complete and actionable"
metrics:
  duration: 2min
  completed: 2026-04-03
  tasks_completed: 2
  files_changed: 2
---

# Phase 02 Plan 02: YAML Wiring + TOU Automation Fix Summary

**One-liner:** Wired temperature sensor and setpoint number into tublemetry.yaml; fixed tou_automation.yaml to use number.set_value with plain degF integers against number.tublemetry_hot_tub_setpoint.

## What Was Built

### Task 1: tublemetry.yaml — temperature sensor and setpoint number entries

**EDIT 1 — temperature key added to existing tublemetry_display sensor entry:**

Added `temperature: name: "Hot Tub Temperature"` inside the existing `platform: tublemetry_display` sensor block, alongside `decode_confidence`. No `device_class`, no `entity_category`, no `state_class` — name only, so HA treats the unit label "degF" as opaque and performs no conversion.

**EDIT 2 — new top-level number: block:**

Added between `sensor:` and `text_sensor:`:

```yaml
number:
  - platform: tublemetry_display
    tublemetry_id: hot_tub_display
    setpoint:
      name: "Hot Tub Setpoint"
      mode: BOX
```

Entity ID derivation: device name "tublemetry" + name "Hot Tub Setpoint" = `number.tublemetry_hot_tub_setpoint`.

All pre-existing top-level keys preserved. No climate entity at any level.

### Task 2: tou_automation.yaml — number entity with degF values

Rewrote all six action blocks:

| Trigger ID    | Time  | Days              | Value |
|---------------|-------|-------------------|-------|
| wd_preheat    | 04:30 | mon-fri           | 104   |
| we_preheat    | 05:00 | sat-sun           | 104   |
| wd_onpeak     | 10:00 | mon-fri           | 96    |
| wd_eve_preheat| 17:30 | mon-fri           | 102   |
| wd_eve_full   | 19:00 | mon-fri           | 104   |
| coast         | 22:00 | all days          | 98    |

Action pattern per block:
```yaml
- action: number.set_value
  target:
    entity_id: number.tublemetry_hot_tub_setpoint
  data:
    value: <integer>
```

All trigger IDs, trigger times, conditions, and weekday filters preserved exactly. Celsius values (40.0, 35.6, 38.9, 36.7) and `climate.tublemetry_hot_tub` references fully removed. Description updated to remove TODO comment.

## Verification Results

- `grep -c "platform: tublemetry_display" esphome/tublemetry.yaml` = 3 (sensor + number + text_sensor — all correct)
- `grep -c "number.set_value" ha/tou_automation.yaml` = 6
- `grep -c "number.tublemetry_hot_tub_setpoint" ha/tou_automation.yaml` = 6
- `grep "climate" esphome/tublemetry.yaml ha/tou_automation.yaml` = nothing
- `uv run pytest tests/ -q` = 218 passed, 0 failures

## Commits

| Task | Hash    | Message                                                         |
|------|---------|-----------------------------------------------------------------|
| 1    | 9456a3f | feat(02-02): add temperature sensor and setpoint number entries to tublemetry.yaml |
| 2    | e40ebba | fix(02-02): replace climate entity with number entity in tou_automation.yaml |

## Deviations from Plan

None — plan executed exactly as written.

The plan's verification note says "Expect 2 lines" for `platform: tublemetry_display` but the pre-existing text_sensor block also contains that pattern, producing 3 total. This is not a deviation — the plan's interface comment only described the sensor block additions; the text_sensor occurrence was pre-existing and unchanged.

## Known Stubs

None. Both data paths are now fully wired:
- `sensor.tublemetry_hot_tub_temperature` — receives display temperature via `temperature_sensor_->publish_state()` in C++
- `number.tublemetry_hot_tub_setpoint` — writes to `ButtonInjector::request_temperature()` in C++
- `tou_automation.yaml` calls `number.set_value` against `number.tublemetry_hot_tub_setpoint` with correct integer degF values

## Self-Check: PASSED
