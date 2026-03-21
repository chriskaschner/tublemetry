---
id: T02
parent: S01
milestone: M001
provides:
  - ESPHome external component (C++ frame parser + 7-segment decoder) for RS-485 display reading
  - Read-only climate entity (climate.hot_tub) exposing current water temperature in HA
  - Six diagnostic sensors: display_string, raw_hex, display_state, decode_confidence, digit_values, last_update
  - Cross-check test verifying C++ lookup table matches Python reference
  - Dual UART config for Pin 5 + Pin 6 via MAX485
  - 10 YAML validation tests preventing ESPHome config regressions
requires: []
affects: []
key_files: []
key_decisions: []
patterns_established: []
observability_surfaces: []
drill_down_paths: []
duration: 5min
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---
# T02: 01-button-injection-mvp 02

**# Phase 1 Plan 2: ESPHome External Component Summary**

## What Happened

# Phase 1 Plan 2: ESPHome External Component Summary

**ESPHome external component with C++ 7-segment decoder ported from Python, read-only climate entity (climate.hot_tub), six diagnostic sensors, dual UART config, and cross-check test -- compiles successfully on ESP32, 56 total tests passing**

## Performance

- **Duration:** ~5 min (across two sessions with human-verify checkpoint)
- **Started:** 2026-03-14T01:28:48Z
- **Completed:** 2026-03-14T01:54:00Z
- **Tasks:** 3 (2 auto + 1 human-verify checkpoint with compilation fixes)
- **Files created:** 11

## Accomplishments
- Complete ESPHome external component with C++ frame parser porting Python decode logic to firmware
- Read-only climate entity exposing current water temperature in Home Assistant thermostat card
- Six diagnostic sensors (display_string, raw_hex, display_state, decode_confidence, digit_values, last_update) for full RS-485 visibility
- Cross-check test verifying C++ SEVEN_SEG_TABLE matches Python reference (prevents decode drift)
- ESPHome compilation verified successfully on ESP32 Arduino framework
- 10 YAML validation tests catching common ESPHome config errors before slow compile
- Full test suite: 56 tests passing (39 Plan 01 + 7 cross-check + 10 YAML validation)

## Task Commits

Each task was committed atomically:

1. **Task 1: ESPHome external component -- Python schema and C++ implementation** - `0b3b0ed` (feat)
2. **Task 2: ESPHome YAML config and compile verification** - `329cb02` (chore)
3. **Task 3: ESPHome compilation fixes and YAML validation tests** - `f8539e4` (fix)

## Files Created/Modified
- `esphome/components/tubtron_display/__init__.py` - ESPHome Python config schema with dual UART references
- `esphome/components/tubtron_display/climate.py` - Climate platform registration (read-only HEAT mode)
- `esphome/components/tubtron_display/sensor.py` - Numeric sensor platform (decode_confidence)
- `esphome/components/tubtron_display/text_sensor.py` - Text sensor platform (display_string, raw_hex, display_state, digit_values, last_update)
- `esphome/components/tubtron_display/tubtron_display.h` - C++ header with TubtronDisplay and TubtronClimate class declarations
- `esphome/components/tubtron_display/tubtron_display.cpp` - C++ implementation: SEVEN_SEG_TABLE, frame parser, state machine, publish-on-change logic
- `esphome/tubtron.yaml` - Main ESPHome config with dual UART, external component, climate, and diagnostic sensors
- `esphome/secrets.yaml` - Placeholder WiFi credentials
- `esphome/.gitignore` - Exclude .esphome build artifacts and secrets
- `tests/test_cross_check.py` - Cross-check test: parses C++ source and verifies byte mappings match Python table
- `tests/test_esphome_yaml.py` - 10 YAML validation tests for ESPHome config structure

## Decisions Made
- TubtronDisplay stores two UARTComponent pointers rather than inheriting from UARTDevice -- dual UART requires explicit pointer management
- TubtronClimate is a separate class from TubtronDisplay; parent component holds climate pointer and drives state updates
- Frame boundary detection uses millis() with >1ms gap (at 115200 baud, 1 byte = 87us, so 1ms gap = ~11 byte-times)
- SEVEN_SEG_TABLE entries formatted one-per-line with SEVEN_SEG_TABLE_START/END markers for cross-check test regex extraction
- Pin 6 data read and discarded to prevent UART buffer overflow (constant refresh pattern not needed for display decoding)
- Switched from SNTP RealTimeClock to millis() uptime for last_update sensor -- simpler, no external time dependency
- Used climate.climate_schema(TubtronClimate) API instead of deprecated climate.CLIMATE_SCHEMA
- Moved platform/board from esphome: block to top-level esp32: block per ESPHome 2024.x deprecation

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Deprecated ESPHome platform/board in esphome: block**
- **Found during:** Task 3 (compilation verification)
- **Issue:** ESPHome 2024.x removed support for `platform`/`board` inside `esphome:` block
- **Fix:** Moved to top-level `esp32:` block with `framework: type: arduino`
- **Files modified:** esphome/tubtron.yaml
- **Verification:** ESPHome compile succeeds
- **Committed in:** f8539e4

**2. [Rule 1 - Bug] climate.CLIMATE_SCHEMA deprecated**
- **Found during:** Task 3 (compilation verification)
- **Issue:** `climate.CLIMATE_SCHEMA` no longer exists; must use `climate.climate_schema()` function
- **Fix:** Changed to `climate.climate_schema(TubtronClimate)` and removed manual `cv.declare_id`
- **Files modified:** esphome/components/tubtron_display/climate.py
- **Verification:** ESPHome compile succeeds
- **Committed in:** f8539e4

**3. [Rule 1 - Bug] Missing ICON_FORMAT_TEXT constant**
- **Found during:** Task 3 (compilation verification)
- **Issue:** `ICON_FORMAT_TEXT` not available in esphome.const
- **Fix:** Replaced with string literal `"mdi:format-text"`
- **Files modified:** esphome/components/tubtron_display/text_sensor.py
- **Verification:** ESPHome compile succeeds
- **Committed in:** f8539e4

**4. [Rule 1 - Bug] RealTimeClock::get_default() not available**
- **Found during:** Task 3 (compilation verification)
- **Issue:** No static accessor for time component; RealTimeClock API differs from expected
- **Fix:** Simplified to millis()-based uptime timestamp, removed time/real_time_clock.h include
- **Files modified:** esphome/components/tubtron_display/tubtron_display.cpp, tubtron_display.h
- **Verification:** ESPHome compile succeeds
- **Committed in:** f8539e4

**5. [Rule 1 - Bug] Deprecated ClimateTraits methods**
- **Found during:** Task 3 (compilation verification)
- **Issue:** `set_supported_modes()` and `set_supports_action()` deprecated in ESPHome 2025.x
- **Fix:** Changed to `add_supported_mode(climate::CLIMATE_MODE_HEAT)`, removed `set_supports_action`
- **Files modified:** esphome/components/tubtron_display/tubtron_display.cpp
- **Verification:** ESPHome compile succeeds
- **Committed in:** f8539e4

**6. [Rule 2 - Missing Critical] YAML validation tests**
- **Found during:** Task 3 (compilation verification)
- **Issue:** No automated way to catch ESPHome YAML config errors before slow compile
- **Fix:** Added 10 YAML validation tests checking deprecated patterns, required sections, UART config
- **Files modified:** tests/test_esphome_yaml.py (new)
- **Verification:** All 10 tests pass
- **Committed in:** f8539e4

---

**Total deviations:** 6 auto-fixed (5 bugs from ESPHome API changes, 1 missing critical test coverage)
**Impact on plan:** All fixes necessary for successful ESPHome compilation. YAML tests prevent regressions. No scope creep.

## Issues Encountered
- ESPHome API has evolved significantly since the plan was written (deprecated CLIMATE_SCHEMA, changed ClimateTraits methods, moved platform/board to top-level block). All five issues resolved during compilation verification in a single commit.

## User Setup Required

Before flashing to hardware:
1. Install ESPHome: `pip install esphome` or via HA addon
2. Update `esphome/secrets.yaml` with real WiFi credentials
3. Compile: `cd esphome && esphome compile tubtron.yaml`
4. Flash: `cd esphome && esphome run tubtron.yaml` (via USB to ESP32)
5. Verify `climate.hot_tub` appears in Home Assistant

## Next Phase Readiness
- Phase 1 complete: RS-485 display reading firmware ready for hardware testing
- Python decode library (Plan 01) and ESPHome component (Plan 02) form complete read path
- Phase 2 (button injection) can build on this foundation for closed-loop control
- Unverified lookup table entries will be finalized after temperature ladder capture session (physical tub access)
- Hardware testing blocked on parts arrival (AliExpress lead time)

## Self-Check: PASSED

All 11 created files verified present. All 3 commit hashes (0b3b0ed, 329cb02, f8539e4) verified in git log. 56 tests pass.

---
*Phase: 01-button-injection-mvp*
*Completed: 2026-03-14*
