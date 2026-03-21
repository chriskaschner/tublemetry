# S02: Firmware Hardening — WiFi, OTA, HA Integration

**Goal:** Production-ready ESPHome firmware with robust WiFi, OTA recovery, HA integration, diagnostic entities, and mock-based test coverage — verified by compilation and automated tests.
**Demo:** `uv run esphome compile esphome/tublemetry.yaml` succeeds, `uv run pytest` passes with new firmware tests including mock display frame verification, YAML schema validation covers all new entities.

## Must-Haves

- Production YAML with WiFi recovery (reboot_timeout, fallback AP, power_save_mode)
- OTA with safe mode explicitly configured (boot failure recovery)
- API encryption with HA reboot timeout
- Diagnostic entities: WiFi signal, uptime, firmware version, IP/SSID/MAC, restart button, safe mode button
- Mock display frame tests exercising the Python decode pipeline with real captured data
- YAML validation tests covering all new entities and config sections
- ESPHome compile gate passing

## Proof Level

- This slice proves: integration
- Real runtime required: no (WiFi radio dead on current board; compile + mock tests are the verification boundary)
- Human/UAT required: no (hardware verification deferred to new board arrival)

## Verification

- `uv run esphome config esphome/tublemetry.yaml` — YAML schema validates
- `uv run esphome compile esphome/tublemetry.yaml` — firmware compiles clean
- `uv run pytest` — all tests pass including new mock frame and YAML tests
- Compile warning check: no errors in build output (warnings from SDK deps acceptable)

## Observability / Diagnostics

- Runtime signals: WiFi on_connect / on_disconnect logging, safe_mode on_safe_mode logging
- Inspection surfaces: WiFi signal sensor, uptime sensor, firmware version text_sensor, IP/SSID/MAC text_sensors
- Failure visibility: reboot_timeout auto-recovery (WiFi 10min, API 15min), safe mode after 10 boot failures
- Redaction constraints: WiFi password and API key in secrets.yaml (not committed)

## Integration Closure

- Upstream surfaces consumed: `esphome/components/tublemetry_display/` (C++ component, Python codegen)
- New wiring introduced in this slice: diagnostic sensors, recovery buttons, WiFi lifecycle hooks
- What remains before the milestone is truly usable end-to-end: hardware verification on working ESP32 board

## Tasks

- [ ] **T01: Production YAML — WiFi, OTA, API, diagnostics** `est:30m`
  - Why: Current YAML is development-quality; needs production WiFi recovery, proper safe mode config, diagnostic entities for remote monitoring, and HA connectivity resilience
  - Files: `esphome/tublemetry.yaml`
  - Do: Add WiFi reboot_timeout + on_connect/on_disconnect logging. Configure safe_mode explicitly (num_attempts: 10, boot_is_good_after: 30s). Add API reboot_timeout: 15min. Add sensor platforms: wifi_signal (60s), uptime. Add text_sensor platforms: version, wifi_info (ip, ssid, mac). Add button platforms: restart, safe_mode. Add binary_sensor: status (API connection). Add on_boot logging. Remove output_power: 20dB (unnecessary with power_save_mode: none).
  - Verify: `uv run esphome config esphome/tublemetry.yaml` exits 0
  - Done when: YAML validates with all new entities, no schema errors

- [ ] **T02: Compile gate — firmware builds clean** `est:15m`
  - Why: YAML validation doesn't catch C++ errors; the full compile is the real integration test between YAML config, Python codegen, and C++ component
  - Files: `esphome/tublemetry.yaml`, `esphome/components/tublemetry_display/*.cpp`
  - Do: Run full ESPHome compile. Fix any compilation errors from new YAML entities. Address the IRAM section attribute warning if possible. Verify firmware.bin is produced.
  - Verify: `uv run esphome compile esphome/tublemetry.yaml` exits 0 and `test -f esphome/.esphome/build/tublemetry/.pioenvs/tublemetry/firmware.bin`
  - Done when: Clean compile, firmware binary exists

- [ ] **T03: Mock frame tests — exercise decode pipeline with captured data** `est:45m`
  - Why: We have real protocol captures from the logic analyzer but no tests that feed captured frame data through the full decode pipeline. Mock tests let us validate firmware logic without hardware.
  - Files: `tests/test_mock_frames.py`, `src/tublemetry/decode.py`
  - Do: Build test fixtures from known captures: steady 105F (0x30,0x7E,0x5B → "105"), Ec mode (0x00,0x4F,0x0D → " Ec"), temperature ladder entries (80-104F). Test full pipeline: raw 24-bit frame → extract 3x7-bit digits → 7-seg decode → display string → temperature extraction → state classification. Test edge cases: blank frames (all zeros), unknown segments ('?'), setpoint flash pattern (temp ↔ blank ↔ setpoint), mode displays (OH, SL, St). Verify decode confidence calculation.
  - Verify: `uv run pytest tests/test_mock_frames.py -v` passes
  - Done when: ≥15 new tests covering temperature decode, mode decode, edge cases, and confidence

- [ ] **T04: YAML validation tests — cover all new config sections** `est:20m`
  - Why: Structural YAML tests catch config regressions (wrong indentation, missing keys, bad entity_category values) before they hit the compiler
  - Files: `tests/test_esphome_yaml.py`
  - Do: Add tests verifying: wifi section has reboot_timeout and power_save_mode. OTA section has platform and password. API section has encryption.key and reboot_timeout. All diagnostic entities have entity_category: "diagnostic". Button platforms (restart, safe_mode) are present. sensor/text_sensor platforms include wifi_signal, uptime, version, wifi_info. safe_mode section exists at top level.
  - Verify: `uv run pytest tests/test_esphome_yaml.py -v` passes
  - Done when: ≥10 new YAML structure tests, all passing

## Files Likely Touched

- `esphome/tublemetry.yaml`
- `esphome/components/tublemetry_display/tublemetry_display.cpp`
- `tests/test_mock_frames.py` (new)
- `tests/test_esphome_yaml.py`
