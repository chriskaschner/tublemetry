---
phase: 02-architecture-fix-ha-integration
plan: 01
subsystem: esphome-component
tags: [cpp, esphome, number-entity, sensor, ha-integration]
dependency_graph:
  requires: [Phase 01 complete — ButtonInjector::request_temperature() confirmed working]
  provides: [TublemetrySetpoint C++ class, temperature sensor setter, number.py codegen platform]
  affects: [tublemetry_display.h, tublemetry_display.cpp, sensor.py, __init__.py]
tech_stack:
  added: [esphome number platform, TublemetrySetpoint class]
  patterns: [number::Number subclass with control() override, sensor pointer injection via setter]
key_files:
  created:
    - esphome/components/tublemetry_display/tublemetry_setpoint.h
    - esphome/components/tublemetry_display/tublemetry_setpoint.cpp
    - esphome/components/tublemetry_display/number.py
  modified:
    - esphome/components/tublemetry_display/tublemetry_display.h
    - esphome/components/tublemetry_display/tublemetry_display.cpp
    - esphome/components/tublemetry_display/sensor.py
    - esphome/components/tublemetry_display/__init__.py
decisions:
  - "No device_class on temperature sensor — omitting device_class prevents HA unit conversion; unit_of_measurement='degF' is treated as an opaque label"
  - "number.py uses try/except around injector lookup — injector may not exist in read-only deployments; exception is silently swallowed"
  - "publish_state() called before request_temperature() in TublemetrySetpoint::control() — optimistic update makes HA reflect the requested value immediately"
metrics:
  duration: 2min
  completed: 2026-04-03
  tasks_completed: 2
  files_changed: 7
---

# Phase 02 Plan 01: C++ + Codegen Layer Summary

**One-liner:** TublemetrySetpoint number entity class and number.py codegen platform; temperature sensor wired into classify_display_state_(); AUTO_LOAD updated; no unit conversion anywhere.

## What Was Built

### Task 1: TublemetrySetpoint C++ class

`tublemetry_setpoint.h` — declares `TublemetrySetpoint` inheriting from `number::Number`:
- `set_button_injector(ButtonInjector *)` setter stores injector pointer
- `void control(float value) override` declared in protected section
- `ButtonInjector *injector_{nullptr}` member

`tublemetry_setpoint.cpp` — implements `control()`:
- `publish_state(value)` first (optimistic HA update)
- Guards: `injector_ != nullptr && injector_->is_configured()`
- `ESP_LOGW` if `request_temperature()` returns false

### Task 2: Five-file wiring

**tublemetry_display.h:**
- Added `#include "esphome/components/number/number.h"`
- Added `set_temperature_sensor(sensor::Sensor *s)` and `set_setpoint_number(number::Number *n)` setters
- Added `sensor::Sensor *temperature_sensor_{nullptr}` and `number::Number *setpoint_number_{nullptr}` members

**tublemetry_display.cpp:**
- `classify_display_state_()`: refactored to extract `temp` before injector block; added `temperature_sensor_->publish_state(temp)` guard after injector call

**sensor.py:**
- Added `CONF_TEMPERATURE = "temperature"` constant
- Added optional `temperature` schema entry: `unit_of_measurement="degF"`, `icon="mdi:thermometer"`, `accuracy_decimals=0` — no `device_class`, no `entity_category`, no `state_class`
- Added `to_code()` branch wiring `set_temperature_sensor()`

**__init__.py:**
- `AUTO_LOAD = ["sensor", "text_sensor", "number"]`

**number.py (new):**
- `TublemetrySetpoint = tublemetry_display_ns.class_("TublemetrySetpoint", number.Number)`
- `CONFIG_SCHEMA` with optional `setpoint` using `number_schema(TublemetrySetpoint, unit_of_measurement="degF", icon="mdi:thermometer")`
- `to_code()` calls `number.new_number(conf, min_value=80.0, max_value=104.0, step=1.0)`, wires injector via try/except, calls `parent.set_setpoint_number(var)`

## Verification Results

- All 218 existing tests pass with no regressions
- No `device_class` in sensor.py temperature entry (confirmed via grep)
- All 7 files created/modified as specified
- Acceptance criteria for both tasks met

## Commits

| Task | Hash | Message |
|------|------|---------|
| 1 | 6dea33a | feat(02-01): add TublemetrySetpoint C++ class |
| 2 | b19af11 | feat(02-01): wire temperature sensor and setpoint number into display component |

## Deviations from Plan

**1. [Rule 1 - Refactor] Extracted temp variable before injector block in classify_display_state_()**

- **Found during:** Task 2
- **Issue:** The original code computed `temp` inside the injector guard. Adding the temperature sensor publish after the injector guard required `temp` to be in scope at that level.
- **Fix:** Moved `float temp = static_cast<float>(atoi(stripped.c_str()))` outside the injector guard, still inside the `is_numeric` block. Both the injector call and the sensor publish now use the same variable.
- **Files modified:** esphome/components/tublemetry_display/tublemetry_display.cpp
- **Commit:** b19af11

No other deviations — plan executed as written.

## Known Stubs

None. All data paths are wired:
- `temperature_sensor_` is set when `sensor.py` includes a `temperature:` entry in YAML
- `setpoint_number_` is set when `number.py` includes a `setpoint:` entry in YAML
- Both are guarded with nullptr checks; nil pointer = sensor not configured in YAML (valid state)

## Self-Check: PASSED
