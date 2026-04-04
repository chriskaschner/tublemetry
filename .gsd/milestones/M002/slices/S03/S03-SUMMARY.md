---
id: S03
parent: M002
milestone: M002
provides:
  - heater/pump/light binary sensor C++ members and setters in TublemetryDisplay
  - binary_sensor.py ESPHome codegen module
  - 36 status-bit tests in tests/test_status_bits.py
  - ha/dashboard.yaml Card 6 status card
requires:
  []
affects:
  - S04
key_files:
  - esphome/components/tublemetry_display/tublemetry_display.h
  - esphome/components/tublemetry_display/tublemetry_display.cpp
  - esphome/components/tublemetry_display/binary_sensor.py
  - esphome/components/tublemetry_display/__init__.py
  - esphome/tublemetry.yaml
  - tests/test_status_bits.py
  - tests/test_esphome_yaml.py
  - ha/dashboard.yaml
key_decisions:
  - p1_full re-extracted from frame_bits outside the checksum scoped block — scoped p1 is out of scope after the block closes
  - int8_t last-state trackers initialized to -1 so first frame always publishes regardless of true/false initial value
  - device_class 'running' confirmed valid in installed ESPHome DEVICE_CLASSES list for pump sensor
  - Test imports use `from tests.test_mock_frames import` (not bare form) to match existing convention
patterns_established:
  - binary_sensor.py pattern mirrors sensor.py: CONF_TUBLEMETRY_ID lookup, Optional per-sensor schema blocks, async to_code with get_variable + new_binary_sensor + cg.add setter call
  - Python mirror tests for C++ bit extraction: extract the same bit-shift formula verbatim into a Python function, test all combinations parametrically
observability_surfaces:
  - Three new HA binary sensors: binary_sensor.tublemetry_hot_tub_heater, binary_sensor.tublemetry_hot_tub_pump, binary_sensor.tublemetry_hot_tub_light
  - Dashboard Card 6 (Hot Tub Status) in ha/dashboard.yaml surfaces all three binary sensors
drill_down_paths:
  - .gsd/milestones/M002/slices/S03/tasks/T01-SUMMARY.md
  - .gsd/milestones/M002/slices/S03/tasks/T02-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-04-04T14:13:56.544Z
blocker_discovered: false
---

# S03: Status Bit Binary Sensors

**Exposed heater, pump, and light as HA binary sensors — bit extraction in C++, ESPHome codegen, YAML config, 36 new tests, and a dashboard status card. 336 tests pass, firmware compiles clean.**

## What Happened

S03 was a clean, low-risk slice with two tasks that proceeded without blockers.

T01 wired the binary sensors end-to-end: added `binary_sensor::BinarySensor` pointer members and set_* setters to `tublemetry_display.h`, added status bit extraction in `process_frame_()` after `classify_display_state_()`, created `binary_sensor.py` following the existing `sensor.py` pattern, updated AUTO_LOAD in `__init__.py`, and added the YAML block to `tublemetry.yaml`. The key implementation detail: `p1_full` must be re-extracted outside the checksum scoped block because the scoped `p1` variable goes out of scope. Last-state trackers (`int8_t`, initialized to -1) guarantee the first frame always publishes regardless of the initial value.

T02 added 36 tests across four classes (TestStatusBitExtraction, TestStatusBitCombinations, TestChecksumCompatibility, TestPublishOnChange) as Python mirrors of the C++ logic, extended `test_esphome_yaml.py` with a binary sensor entity presence test, and appended a Hot Tub Status card (Card 6) to `ha/dashboard.yaml`. Import path required `from tests.test_mock_frames import` — bare form fails because `tests/` is not in pythonpath.

Slice-level verification: 336 pytest tests pass in 0.40s, ESPHome compile succeeds in 10.35s with `[SUCCESS]`. No regressions against the pre-S03 baseline.

## Verification

Full pytest suite (336 tests, 0 failures): `uv run pytest tests/ --ignore=tests/test_ladder_capture.py -v`. ESPHome compile: `/Users/chriskaschner/Documents/GitHub/tubtron/.venv/bin/esphome compile esphome/tublemetry.yaml 2>&1 | grep -E '\[SUCCESS\]|ERROR'` → `[SUCCESS] Took 10.35 seconds`.

## Requirements Advanced

- R005 — Heater status (p1 bit 2) extracted and published as BinarySensor with on-change filtering. 9 extraction tests + compile pass.
- R006 — Pump status (p4 bit 2) extracted and published as BinarySensor with on-change filtering. 9 extraction tests + compile pass.
- R007 — Light status (p4 bit 1) extracted and published as BinarySensor with on-change filtering. 9 extraction tests + compile pass.
- R010 — 336 tests pass with zero regressions after S03 changes.
- R012 — All existing entity IDs preserved. New binary sensor entities added with distinct IDs.

## Requirements Validated

- R005 — Bit 2 of p1 extracted as heater_on in process_frame_(). TestStatusBitExtraction::test_heater_bit_set/cleared pass. Firmware compiles clean.
- R006 — Bit 2 of p4 extracted as pump_on. TestStatusBitExtraction::test_pump_bit_set/cleared pass. Firmware compiles clean.
- R007 — Bit 1 of p4 extracted as light_on. TestStatusBitExtraction::test_light_bit_set/cleared pass. Firmware compiles clean.

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

T02 import path: task plan specified bare `from test_mock_frames import`; changed to `from tests.test_mock_frames import` to match existing test convention. No behavioral difference.

## Known Limitations

Heater hysteresis (R014, deferred): the heater sensor publishes immediately on bit change with no debounce delay. If rapid heater on/off toggling is observed in HA, R014 should be promoted. Status bit positions (heater=p1 bit 2, pump=p4 bit 2, light=p4 bit 1) are sourced from kgstorm analysis and have not yet been verified against live VS300FL4 wire captures — to be confirmed during first OTA flash and live observation.

## Follow-ups

Verify status bit positions (heater/pump/light) match live VS300FL4 wire data after OTA flash. If heater shows rapid flicker in HA, implement R014 hysteresis.

## Files Created/Modified

- `esphome/components/tublemetry_display/tublemetry_display.h` — Added binary_sensor include, three BinarySensor pointer members, set_* setters, int8_t last-state trackers
- `esphome/components/tublemetry_display/tublemetry_display.cpp` — Added status bit extraction block in process_frame_() after classify_display_state_() call
- `esphome/components/tublemetry_display/binary_sensor.py` — New ESPHome codegen module for heater/pump/light binary sensors
- `esphome/components/tublemetry_display/__init__.py` — Added binary_sensor to AUTO_LOAD list
- `esphome/tublemetry.yaml` — Added tublemetry_display binary sensor block with heater/pump/light entries
- `tests/test_status_bits.py` — New: 36 tests for bit extraction, all 8 status combinations, checksum compatibility, publish-on-change
- `tests/test_esphome_yaml.py` — Extended TestEsphomeYaml with test_tublemetry_binary_sensors_present
- `ha/dashboard.yaml` — Appended Card 6 Hot Tub Status with heater/pump/light entities
