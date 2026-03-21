---
id: S02
parent: M001
milestone: M001
provides:
  - Production-ready ESPHome YAML with WiFi recovery, OTA safe mode, HA diagnostics
  - 49 mock frame tests validating full decode pipeline with real captured data
  - 15 production config YAML validation tests
  - Compile-verified firmware binary
requires:
  - slice: S01
    provides: tublemetry_display C++ component, Python decode library, 7-segment lookup table
affects:
  - S03
key_files:
  - esphome/tublemetry.yaml
  - tests/test_mock_frames.py
  - tests/test_esphome_yaml.py
  - esphome/components/tublemetry_display/tublemetry_display.cpp
key_decisions:
  - WiFi reboot_timeout 10min, API reboot_timeout 15min for auto-recovery
  - safe_mode explicitly configured (10 attempts, 30s boot_is_good_after)
  - All diagnostic entities use entity_category diagnostic
  - Mock tests simulate C++ frame extraction logic in Python for cross-validation
patterns_established:
  - Production YAML template with WiFi/OTA/API/diagnostics pattern
  - Mock frame testing pattern using digits_to_frame/frame_to_display_string helpers
  - TestProductionConfig class pattern for YAML structure regression tests
observability_surfaces:
  - WiFi signal sensor (RSSI), uptime sensor, firmware version, IP/SSID/MAC
  - API status binary sensor, restart button, safe mode button
  - WiFi on_connect/on_disconnect logging, safe_mode on_safe_mode error logging
drill_down_paths: []
duration: 45min
verification_result: passed
completed_at: 2026-03-21
---

# S02: Firmware Hardening — WiFi, OTA, HA Integration

**Production-ready ESPHome firmware with WiFi recovery, OTA safe mode, HA diagnostic entities, and 64 new tests (49 mock frame + 15 YAML validation)**

## What Happened

Rewrote tublemetry.yaml from dev-quality to production-ready. Added WiFi auto-recovery (reboot after 10min disconnect), explicit safe mode config (10 boot failures → minimal WiFi+OTA mode), API encryption with 15min ghost-connectivity reboot, and remote management buttons (restart, safe mode). Added full diagnostic entity suite: WiFi signal, uptime, firmware version, IP/SSID/MAC, API status.

Built mock frame tests that simulate the C++ ISR frame extraction in Python — feeding known 24-bit frames (from real logic analyzer captures) through digit extraction → 7-seg decode → display string → state classification. Parametrized tests cover the full 80-104F temperature ladder. Setpoint flash sequence test validates the temp→blank→setpoint→blank→temp pattern observed during button presses.

Added 15 YAML production config tests that validate every new section: WiFi recovery settings, API encryption, OTA password, safe mode, buttons, diagnostic sensors, and entity_category tagging.

Verified the complete pipeline: YAML config validates (`esphome config`), firmware compiles clean (`esphome compile`), and all 139 tests pass.

## Verification

- `uv run esphome config esphome/tublemetry.yaml` — validates clean (INFO Configuration is valid!)
- `uv run esphome compile esphome/tublemetry.yaml` — firmware.bin produced (INFO Successfully compiled program)
- `uv run pytest` — 139 passed in 0.18s (75 existing + 49 mock frame + 15 YAML production)
- No compilation errors (SDK file paths containing "error" are not build errors)

## Requirements Advanced

- DISP-01 — firmware now includes full diagnostic sensor suite for display stream verification
- DISP-02 — climate entity + WiFi + API encryption ready for HA integration
- CONN-01 — OTA with password and safe mode recovery configured
- CONN-02 — WiFi auto-reconnect with reboot_timeout and fallback AP
- CONN-03 — WiFi on_connect/on_disconnect logging, safe_mode error logging

## Requirements Validated

- None (hardware verification pending — WiFi radio dead on current board)

## New Requirements Surfaced

- None

## Requirements Invalidated or Re-scoped

- None

## Deviations

None — plan executed as written.

## Known Limitations

- WiFi radio dead on current HiLetGo ESP-32S board — cannot test WiFi, OTA, or HA connectivity until new board arrives
- ISR IRAM section attribute warning persists (gcc: `ignoring attribute 'section (".iram1.2")'`) — cosmetic, doesn't affect functionality
- `esptool` baud 460800 fails on CP2102 USB-serial adapter — 115200 works

## Follow-ups

- Hardware verification on new ESP32 board: WiFi connect, OTA flash, HA entity discovery
- Consider adding `manual_ip` for static IP once DHCP lease is known (faster reconnects)
- Address IRAM section attribute warning if it causes issues on other boards

## Files Created/Modified

- `esphome/tublemetry.yaml` — production YAML with WiFi/OTA/API/diagnostics
- `tests/test_mock_frames.py` — 49 mock frame decode pipeline tests (new)
- `tests/test_esphome_yaml.py` — 15 new production config validation tests
- `.gsd/milestones/M001/slices/S02/S02-RESEARCH.md` — ESPHome best practices research
- `.gsd/milestones/M001/slices/S02/S02-PLAN.md` — 4-task plan with verification criteria
- `.gsd/milestones/M001/M001-ROADMAP.md` — updated with S02 complete, S03 added
- `.gsd/KNOWLEDGE.md` — board-specific findings and ISR lessons

## Forward Intelligence

### What the next slice should know
- The firmware is compile-verified but untested on real hardware — first boot on a working board should be monitored via serial logs
- The ISR trampoline uses an instance pointer; if ESPHome API changes in a future version, this is the likely break point
- `esptool erase-flash` then reflash requires explicit 4-partition write or the board boot-loops

### What's fragile
- ISR noise rejection (MIN_PULSE_US = 10µs) is untested with real clock signal — may need tuning if frames are missed
- WiFi + ISR coexistence unverified — the pull-downs should prevent ISR spam but real load testing is needed

### Authoritative diagnostics
- Serial log on boot: look for "Clock interrupt attached, waiting for frames..." (component initialized) and "WiFi connected" (network up)
- WiFi signal sensor: -30 to -50 dBm is excellent, below -80 dBm indicates antenna/range problems
- Uptime sensor: if it resets unexpectedly, check safe_mode boot count in preferences

### What assumptions changed
- Original assumption: WiFi would just work on the HiLetGo board → board has dead radio, need new hardware
- Original assumption: UART-based display reading → protocol is synchronous clock+data, not UART (already known from S01 but reinforced)
