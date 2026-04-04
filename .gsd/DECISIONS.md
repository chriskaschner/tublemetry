- GS510SZ reference encoding used as base for unverified 7-segment mappings (bit6=a through bit0=g)
- Dp bit (bit 7) masked before lookup -- 0x30 and 0xB0 decode to same character
- DisplayState uses pure-function update pattern returning new state objects
- Temperature outside 80-120F flagged as low confidence rather than rejected
- TubtronDisplay stores two UARTComponent pointers rather than inheriting from UARTDevice (dual UART)
- TubtronClimate is a separate class; parent TubtronDisplay holds climate pointer
- Frame boundary detection uses millis() gap > 1ms (not micros())
- SEVEN_SEG_TABLE formatted with markers for cross-check test parseability
- Pin 6 data read and discarded to prevent UART buffer overflow
- Timestamp sensor uses millis uptime instead of SNTP (simpler, no RealTimeClock dependency)
- climate.climate_schema() used instead of deprecated CLIMATE_SCHEMA
- Top-level esp32: block used instead of deprecated platform/board in esphome: block
- OTA indentation was already correct in tubtron.yaml (no fix needed -- verification report was based on stale data)
- Ladder capture byte_3_value extracts byte at index 3 (tens digit for 3-digit temps); ones digit derived from temperature % 10 in generate_lookup_update
- pytest pythonpath config added to pyproject.toml for importing 485/scripts modules

---

## Decisions Table

| # | When | Scope | Decision | Choice | Rationale | Revisable? | Made By |
|---|------|-------|----------|--------|-----------|------------|---------|
| D001 |  | architecture | Temperature unit handling between ESP32, ESPHome, and Home Assistant | ESP32 publishes raw integer display values with no unit conversion. HA owns the meaning (°F). ESPHome climate component is the wrong abstraction — to be replaced with sensor + number entities. | ESP32 is a display decoder, not a thermostat. It reads 7-segment bytes and outputs integers. The display shows 78, the ESP32 publishes 78. HA declares the unit as °F. ESPHome's climate component assumes Celsius internally and forces a conversion chain that causes double-conversion bugs. Using sensor + number keeps the stack honest: no conversions anywhere, faithful mirror of the physical display. | No — this is a fundamental design principle for the system | collaborative |
| D002 | M002 | arch | Stability filtering threshold | Require 3 consecutive identical decoded frames before publishing any value (STABLE_THRESHOLD = 3) | Matches kgstorm's proven threshold. At 60Hz frame rate, 3 frames = 50ms latency — imperceptible to users but eliminates single-frame noise. Prevents transient misreads from polluting HA sensor history. | Yes | collaborative |
