# T02: 01-button-injection-mvp 02

**Slice:** S01 — **Milestone:** M001

## Description

Build the ESPHome external component that reads the VS300FL4's RS-485 display stream and surfaces the current water temperature as a read-only climate entity in Home Assistant, with diagnostic sensors.

Purpose: This is the firmware that runs on the ESP32. It ports the Python decode logic (verified in Plan 01) to C++, wraps it in ESPHome's external component framework, and exposes a climate entity (`climate.hot_tub`) plus diagnostic sensors to HA. The component reads dual UARTs (Pin 5 + Pin 6), decodes frames at ~60Hz internally, and publishes state changes only.

Output: A complete ESPHome project in `esphome/` -- compilable YAML config, Python component schema, C++ implementation, ready to flash to ESP32. Plus a cross-check test verifying the C++ lookup table matches the Python reference.

## Must-Haves

- [ ] "ESPHome compiles the tubtron.yaml config without errors"
- [ ] "The external component reads dual UARTs (Pin 5 and Pin 6) at 115200 baud"
- [ ] "Frame parser in C++ decodes 8-byte frames using the same lookup table verified in Python"
- [ ] "Climate entity exposes current_temperature (read-only, HEAT mode, 80-104F range)"
- [ ] "Diagnostic sensors expose raw hex, display string, display state, decode confidence, last update timestamp, and per-digit breakdown"
- [ ] "State publishes only on change (not every 60Hz frame)"
- [ ] "Non-temperature displays (OH, ICE, --) keep last valid temperature in climate entity"
- [ ] "User can see current water temperature in HA thermostat card"
- [ ] "C++ byte mappings cross-checked against Python SEVEN_SEG_TABLE by automated test"

## Files

- `esphome/tubtron.yaml`
- `esphome/secrets.yaml`
- `esphome/components/tubtron_display/__init__.py`
- `esphome/components/tubtron_display/climate.py`
- `esphome/components/tubtron_display/sensor.py`
- `esphome/components/tubtron_display/text_sensor.py`
- `esphome/components/tubtron_display/tubtron_display.h`
- `esphome/components/tubtron_display/tubtron_display.cpp`
- `tests/test_cross_check.py`
