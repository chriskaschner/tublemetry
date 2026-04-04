---
id: T02
parent: S03
milestone: M002
provides: []
requires: []
affects: []
key_files: ["tests/test_status_bits.py", "tests/test_esphome_yaml.py", "ha/dashboard.yaml"]
key_decisions: ["Used `from tests.test_mock_frames import` (not bare form) to match existing convention — bare import fails because tests/ is not in pythonpath (only 485/scripts is)"]
patterns_established: []
drill_down_paths: []
observability_surfaces: []
duration: ""
verification_result: "uv run pytest tests/ --ignore=tests/test_ladder_capture.py -v — 336 passed in 0.37s, zero failures."
completed_at: 2026-04-04T14:12:05.287Z
blocker_discovered: false
---

# T02: Added 36 new tests covering heater/pump/light bit extraction, all 8 status combinations, checksum compatibility, and publish-on-change; extended YAML entity test; appended status card to dashboard — 336 passed, 0 failures

> Added 36 new tests covering heater/pump/light bit extraction, all 8 status combinations, checksum compatibility, and publish-on-change; extended YAML entity test; appended status card to dashboard — 336 passed, 0 failures

## What Happened
---
id: T02
parent: S03
milestone: M002
key_files:
  - tests/test_status_bits.py
  - tests/test_esphome_yaml.py
  - ha/dashboard.yaml
key_decisions:
  - Used `from tests.test_mock_frames import` (not bare form) to match existing convention — bare import fails because tests/ is not in pythonpath (only 485/scripts is)
duration: ""
verification_result: passed
completed_at: 2026-04-04T14:12:05.287Z
blocker_discovered: false
---

# T02: Added 36 new tests covering heater/pump/light bit extraction, all 8 status combinations, checksum compatibility, and publish-on-change; extended YAML entity test; appended status card to dashboard — 336 passed, 0 failures

**Added 36 new tests covering heater/pump/light bit extraction, all 8 status combinations, checksum compatibility, and publish-on-change; extended YAML entity test; appended status card to dashboard — 336 passed, 0 failures**

## What Happened

Created tests/test_status_bits.py with Python mirrors of the C++ bit-extraction logic from process_frame_(). Four test classes: TestStatusBitExtraction (9 tests) for individual heater/pump/light on and off cases; TestStatusBitCombinations (11 tests) parametrized over all 8 status combinations; TestChecksumCompatibility (8 tests) verifying status=0b100/0b010/0b110 pass the gate and status=0b001 fails; TestPublishOnChange (8 tests) mirroring the C++ int8_t last-state tracking. Extended TestEsphomeYaml with test_tublemetry_binary_sensors_present. Appended Card 6 (Hot Tub Status) to ha/dashboard.yaml. Import path required from tests.test_mock_frames import to match existing convention — bare import fails because tests/ is not in pythonpath.

## Verification

uv run pytest tests/ --ignore=tests/test_ladder_capture.py -v — 336 passed in 0.37s, zero failures.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `uv run pytest tests/ --ignore=tests/test_ladder_capture.py -v 2>&1 | tail -5` | 0 | ✅ pass | 370ms |


## Deviations

Import path: task plan specified bare `from test_mock_frames import`. Changed to `from tests.test_mock_frames import` to match convention in test_frame_integrity.py and avoid ModuleNotFoundError. No behavioral difference.

## Known Issues

None.

## Files Created/Modified

- `tests/test_status_bits.py`
- `tests/test_esphome_yaml.py`
- `ha/dashboard.yaml`


## Deviations
Import path: task plan specified bare `from test_mock_frames import`. Changed to `from tests.test_mock_frames import` to match convention in test_frame_integrity.py and avoid ModuleNotFoundError. No behavioral difference.

## Known Issues
None.
