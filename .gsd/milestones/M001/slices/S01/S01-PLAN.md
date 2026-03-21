# S01: Button Injection Mvp

**Goal:** Build the Python decode library for the VS300FL4 RS-485 display stream.
**Demo:** Build the Python decode library for the VS300FL4 RS-485 display stream.

## Must-Haves


## Tasks

- [x] **T01: 01-button-injection-mvp 01** `est:4min`
  - Build the Python decode library for the VS300FL4 RS-485 display stream. This is the core logic that converts raw UART bytes into meaningful display readings (temperature, OH, ICE, etc.).

Purpose: The decode logic must be correct before porting to C++ for the ESPHome component. Python enables thorough TDD with fast iteration. The 7-segment lookup table uses confirmed mappings (0x30="1", 0x70="7") and placeholders for unverified bytes that will be filled in after the temperature ladder capture.

Output: A tested Python library (`src/tubtron/`) with three modules -- `decode.py` (7-segment lookup), `frame_parser.py` (8-byte frame parsing), `display_state.py` (state machine for temperature persistence). All exercised by pytest tests.
- [x] **T02: 01-button-injection-mvp 02** `est:5min`
  - Build the ESPHome external component that reads the VS300FL4's RS-485 display stream and surfaces the current water temperature as a read-only climate entity in Home Assistant, with diagnostic sensors.

Purpose: This is the firmware that runs on the ESP32. It ports the Python decode logic (verified in Plan 01) to C++, wraps it in ESPHome's external component framework, and exposes a climate entity (`climate.hot_tub`) plus diagnostic sensors to HA. The component reads dual UARTs (Pin 5 + Pin 6), decodes frames at ~60Hz internally, and publishes state changes only.

Output: A complete ESPHome project in `esphome/` -- compilable YAML config, Python component schema, C++ implementation, ready to flash to ESP32. Plus a cross-check test verifying the C++ lookup table matches the Python reference.
- [x] **T03: 01-button-injection-mvp 03** `est:5min`
  - Close verification gaps from 01-VERIFICATION.md: fix premature requirement status, add structural YAML test to prevent indentation-as-nesting regressions, and prepare temperature ladder capture tooling so everything is ready when hardware arrives.

Purpose: The verification found REQUIREMENTS.md prematurely marks DISP-01/DISP-02 as complete, the existing YAML tests miss structural issues (key nesting), and no structured capture tooling exists for the critical ladder capture session. These are all code-actionable fixes that do not require hardware.

Output: Updated REQUIREMENTS.md, enhanced YAML tests, tested ladder capture script.

## Files Likely Touched

- `pyproject.toml`
- `tests/conftest.py`
- `tests/test_decode.py`
- `tests/test_frame_parser.py`
- `tests/test_display_state.py`
- `src/tubtron/__init__.py`
- `src/tubtron/decode.py`
- `src/tubtron/frame_parser.py`
- `src/tubtron/display_state.py`
- `esphome/tubtron.yaml`
- `esphome/secrets.yaml`
- `esphome/components/tubtron_display/__init__.py`
- `esphome/components/tubtron_display/climate.py`
- `esphome/components/tubtron_display/sensor.py`
- `esphome/components/tubtron_display/text_sensor.py`
- `esphome/components/tubtron_display/tubtron_display.h`
- `esphome/components/tubtron_display/tubtron_display.cpp`
- `tests/test_cross_check.py`
- `.planning/REQUIREMENTS.md`
- `tests/test_esphome_yaml.py`
- `485/scripts/ladder_capture.py`
- `tests/test_ladder_capture.py`
