# S02 Research: Firmware Hardening — WiFi, OTA, HA Integration

## Current State

### What Works
- ESPHome firmware compiles and flashes to ESP32 (HiLetGo ESP-32S, ESP32-D0WDQ6 rev1)
- Tublemetry display component initializes: ISR attaches on GPIO16 (clock) / GPIO17 (data)
- 7-segment lookup table: 21 entries, 16 confirmed via ladder capture
- API encryption configured, OTA password set
- Safe mode auto-enabled by OTA component (default: 10 boot failures)
- 75 Python tests passing (decode, frame parser, display state, cross-check, ladder capture, YAML structure)

### What Doesn't Work
- WiFi radio on this specific ESP32 board is dead (zero networks found in scan, confirmed with bare-bones firmware, full flash erase + reflash, power_save_mode: none, output_power: 20dB — still zero networks)
- Cannot test OTA, HA connection, or API until a working board arrives (AliExpress order in transit)
- ISR trampoline had wrong signature (fixed: now passes instance pointer)
- Floating GPIO pins caused potential ISR noise (fixed: pull-downs enabled, MIN_PULSE_US debounce added)

### Board-Specific Finding
- ESP32-D0WDQ6 revision v1.0, MAC: 7C:9E:BD:ED:27:10
- `esptool erase_flash` then reflash caused RTCWDT_RTC_RESET boot loop — required explicit 4-partition flash (bootloader @ 0x1000, partitions @ 0x8000, boot_app0 @ 0xe000, firmware @ 0x10000)
- esp-idf framework caused immediate boot loop on this board; Arduino framework boots fine
- Baud rate 460800 fails on this USB-serial adapter; 115200 works

## ESPHome Production Best Practices (from docs)

### WiFi
- `power_save_mode: none` — most reliable, slightly higher power draw
- `reboot_timeout: 10min` — auto-reboot if WiFi stays disconnected (default: 15min)
- `manual_ip` — static IP eliminates DHCP dependency, faster reconnects
- `on_connect` / `on_disconnect` — triggers for logging or LED status
- `fast_connect: true` — skip scanning, connect directly (only useful if BSSID known)
- Fallback AP mode auto-enabled when `ap:` block is present

### OTA & Safe Mode
- `safe_mode` auto-included with `ota` config since ESPHome 2024.6.0
- Default: 10 boot failures → enters safe mode (WiFi + OTA only, no custom components)
- `boot_is_good_after: 30s` — a boot that survives 30s counts as successful
- Safe mode button available as `button.safe_mode` platform
- OTA password protects against unauthorized firmware uploads

### API & HA Connection
- `api.encryption.key` — mandatory for production (prevents network sniffing)
- `api.reboot_timeout: 15min` — reboot if HA doesn't connect (catches ghost connectivity)
- `api.connected` condition available for automations
- `binary_sensor.status` — exposes connection status to HA

### Diagnostic Entities (standard practice)
- `sensor.wifi_signal` — RSSI in dBm, tracks connectivity quality
- `sensor.uptime` — seconds since boot, catches unexpected restarts
- `text_sensor.version` — ESPHome firmware version string
- `text_sensor.wifi_info` — IP address, SSID, MAC (diagnostic category)
- `button.restart` — remote reboot capability
- `button.safe_mode` — remote safe mode entry

## Available Test Data for Mocking

### Sigrok Logic Analyzer Captures
- `485/examples/steady_105F.csv` — 10 frames of "105" temperature display (1MHz, 2ch)
- `485/examples/mode_Ec.csv` — 10 frames of "Ec" economy mode (1MHz, 2ch)
- `485/captures/` — 43 ladder capture CSVs covering temperatures 80-104F

### Decoded Protocol Reference
- Frame: 24 bits, MSB-first, 60Hz refresh rate
- Layout: [digit1:7][digit2:7][digit3:7][status:3]
- Clock pulses ~37µs apart within frame, ~16.7ms gap between frames
- Known display states: temperature (80-104), blank, OH, Ec, SL, St
- Setpoint flash pattern: actual temp ↔ blank ↔ setpoint (during button press)

### Mock Testing Strategy
- Python tests: decode library already has full coverage with known byte values
- C++ compile test: `uv run esphome compile` validates YAML + component compilation
- YAML validation: `uv run esphome config` checks schema without compiling
- Protocol simulation: can generate test frames from known byte sequences for future hardware-in-loop tests

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| WiFi radio dead on only board | Can't test connectivity | All config is validatable via compile; new board in transit |
| OTA bricking on first deploy | Lose physical access | Safe mode auto-enabled; keep USB cable connected for initial deploys |
| HA API version mismatch | Entity registration fails | ESPHome 2026.2.4 matches current HA; version sensor tracks this |
| ISR starves WiFi task | WiFi drops under load | Pull-downs + noise filter already added; can add ISR rate limiting |
| Flash partition corruption | Boot loop | Keep `esptool erase-flash` + 4-partition flash procedure documented |
