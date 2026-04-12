# Technology Stack

**Project:** Tubtron -- ESP32 Hot Tub Automation
**Researched:** 2026-03-13

## Recommended Stack

### ESPHome Firmware (Core)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| ESPHome | 2026.2.x (latest stable) | Firmware framework, HA integration, OTA | Native Home Assistant API, YAML-driven, massive community, OTA updates. The only serious option for ESP32+HA projects. | HIGH |
| ESP-IDF framework | default (via ESPHome) | Underlying ESP32 framework | ESP-IDF became ESPHome's default for ESP32 in 2026.1.0. Produces 40% smaller binaries and 2-3x faster compiles vs Arduino. No reason to override. | HIGH |
| ESP32 WROOM-32 (esp32dev) | N/A | Target hardware | Already ordered. Use `variant: esp32` in ESPHome config. The `board: esp32dev` setting is optional since ESPHome auto-fills it from variant. | HIGH |

### ESPHome Components (Phase 1: Button Injection)

| Component | Purpose | Why | Confidence |
|-----------|---------|-----|------------|
| `external_components` (local) | Custom climate entity for VS300FL4 | ESPHome's built-in climate platforms (thermostat, bang_bang, PID) all require sensor feedback and implement their own heating control. The VS300FL4 already has its own thermostat -- we only set the setpoint. A minimal custom climate component exposes `target_temperature` to HA without fighting the board's control logic. | HIGH |
| `output.gpio` | Drive photorelay LED inputs | Each GPIO drives one AQY212EH photorelay via 680R resistor. Simple on/off, no PWM needed. | HIGH |
| `globals` (restore_value) | Persist last commanded setpoint across reboots | ESP32 stores target temp in NVS flash. On boot, reports stored value to HA. Prevents "unknown state" after power cycles. | HIGH |
| `api` | Home Assistant native integration | Encryption key required (base64, 32-byte). Password auth removed in 2026.1.0. Auto-discovery via mDNS. | HIGH |
| `ota.esphome` | Over-the-air firmware updates | Password-protected OTA. Essential for iterating on firmware without physical access to the tub enclosure. | HIGH |
| `wifi` | Network connectivity | Standard WiFi with fallback AP mode. Use `!secret` for credentials. | HIGH |
| `logger` | Serial debug output | Essential during prototyping for timing characterization. Reduce to WARN in production to save resources. | HIGH |

### ESPHome Components (Phase 2: Display Reading)

| Component | Purpose | Why | Confidence |
|-----------|---------|-----|------------|
| Extended external component | Add RS-485 synchronous protocol decoder to existing climate component | No built-in ESPHome component handles the VS300FL4's clock+data protocol. Add ISR-driven frame decoder to the C++ component. Feeds `current_temperature` into the existing climate entity. | HIGH |
| `uart` | Hardware UART for RS-485 data reception | ESP32 UART1 receives display data via MAX485 transceiver. 115200 baud, 8N1. ESPHome's UART component handles hardware configuration. | HIGH |

### Home Assistant (TOU Automation)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Home Assistant | 2026.3.x (latest) | Automation platform | Already the target platform. TOU scheduling is straightforward HA automation. | HIGH |
| `climate.set_temperature` | Service call in automations | Standard HA climate action. Set target temp on time trigger with weekday conditions. Works because we expose a climate entity, not a raw number. | HIGH |
| `automation` (time trigger) | TOU schedule execution | Two automations: 10am weekdays -> 99F, evening (before use) -> 104F. Time trigger + condition on weekday. | HIGH |
| `input_number` (optional) | User-adjustable TOU temps | Allows changing the on-peak/off-peak targets from the HA dashboard without editing automations. Nice-to-have, not critical for MVP. | MEDIUM |

### Python Analysis Tools (Existing)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Python | 3.10+ | RS-485 protocol analysis scripts | Already in codebase (485/scripts/). Keep using for offline analysis. | HIGH |
| uv | latest | Python package/environment management | User preference per CLAUDE.md. Use for managing pyserial, numpy dependencies. | HIGH |
| pyserial | latest | Serial communication with RS-485 adapter | Already used in capture scripts. | HIGH |
| numpy | latest | Logic analyzer CSV analysis | Already used in decode_7seg.py. | HIGH |

### Development Tools

| Technology | Purpose | Why | Confidence |
|------------|---------|-----|------------|
| ESPHome CLI (`pip install esphome`) | Compile and flash firmware | Can validate YAML and compile without hardware. Install via `uv pip install esphome`. | HIGH |
| ESPHome Dashboard (optional) | Web UI for managing devices | Runs as HA add-on or standalone Docker. Nice for OTA but CLI works fine. | MEDIUM |
| PlatformIO (implicit) | Build system under ESPHome | ESPHome uses PlatformIO internally. No direct interaction needed. | HIGH |

## Architecture Decision: Custom Climate Component from Phase 1

The central design question is how to expose the hot tub to Home Assistant. After evaluating all options:

| Approach | Verdict | Reason |
|----------|---------|--------|
| `climate.thermostat` with dummy sensor | REJECTED | Thermostat platform implements its own heating control logic with hysteresis, deadband, and PID. The hot tub board already has its own thermostat. Two control loops fighting each other is dangerous and wasteful. |
| `climate.bang_bang` | REJECTED | Same problem -- implements heating/cooling control logic. We only set the target temperature. |
| `climate.pid` | REJECTED | Same problem, plus requires actual sensor feedback for the PID algorithm to work at all. |
| Template climate (feature request #2783) | NOT AVAILABLE | Requested but not merged into ESPHome as of 2026.2. Would be ideal if it existed. |
| `number.template` entity | CONSIDERED | Simple and honest, but HA treats it as a raw number, not a climate device. No thermostat card, no HVAC mode, no native `climate.set_temperature` service call. Would need migration to climate entity later. |
| **Custom external climate component** | **CHOSEN** | A minimal C++ class extending `climate::Climate` + `Component`. Phase 1: only `target_temperature` (no `current_temperature`). Phase 2: add `current_temperature` from display reading. HA gets a proper climate entity from day one -- thermostat card, `climate.set_temperature`, correct entity type. The C++ is ~100-200 lines for Phase 1. |

**Key insight:** A custom climate component does NOT need to implement heating control logic. It just needs to:
1. Accept a target temperature from HA
2. Execute the re-home + count-up button sequence
3. Report the target temperature back to HA
4. Expose `heat` mode (the board is always heating/maintaining)

This is simpler than it sounds. The Ylianst/ESP-IQ2020 and brianfeucht/esphome-balboa-spa projects both follow this exact pattern.

## Why ESP-IDF, Not Arduino

ESP-IDF became the default ESP32 framework in ESPHome 2026.1.0. Benefits:
- 40% smaller binaries (critical -- Phase 2 custom component will add significant code)
- 2-3x faster compile times during development iteration
- Arduino is now integrated as an ESP-IDF component internally, so Arduino APIs remain available if needed
- No components in this project require Arduino-only features

Do NOT explicitly set `type: arduino` unless a specific component demands it.

## Why External Component, Not Lambda

The button injection re-home sequence and (later) the synchronous protocol decoder require:
- State machine for press sequencing (Phase 1) and frame assembly (Phase 2)
- GPIO interrupt handlers with IRAM_ATTR (Phase 2)
- Non-blocking timing (yield to event loop between presses)
- Testable, maintainable C++ code

ESPHome lambdas are limited to single expressions or short inline C++. They cannot define ISR handlers, maintain complex state machines, or be unit-tested. A proper external component with `__init__.py` + `climate.py` + C++ source files is the right structure from the start.

Reference: MagnusPer/Balboa-GS510SZ uses this ISR-driven approach for the GS-series (same protocol family).

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Firmware framework | ESPHome | Arduino IDE + MQTT | Massive maintenance burden. No native HA climate entity. No OTA without extra code. ESPHome handles all of this. |
| Firmware framework | ESPHome | Tasmota | Tasmota is device-focused (smart plugs, bulbs). Poor support for custom protocols. No equivalent to ESPHome external components. |
| Firmware framework | ESPHome | MicroPython | No native HA integration. Poor real-time performance for ISR-driven protocol decoding. Python on ESP32 is too slow for bit-banging. |
| HA integration | ESPHome native API | MQTT | Extra broker to maintain. No auto-discovery of entity types. ESPHome's native API is faster, simpler, and more feature-rich. |
| ESP32 framework | ESP-IDF (default) | Arduino | Arduino produces larger binaries and slower compiles. ESP-IDF is now default. No benefit to overriding. |
| Entity type | Custom climate component | number.template | Climate entity gives HA a thermostat card, proper HVAC mode, and standard `climate.set_temperature` service. Number entity would require migration later. |
| Phase 2 decode | External component (C++) | ESPHome lambda | Lambdas cannot use IRAM_ATTR, cannot define ISR handlers, cannot maintain complex state machines cleanly. |

## Installation

### ESPHome Development Environment

```bash
# Install ESPHome CLI via uv
uv pip install esphome

# Validate configuration without hardware
esphome config tubtron.yaml

# Compile without uploading (verify it builds)
esphome compile tubtron.yaml

# Flash via USB (first time)
esphome run tubtron.yaml

# Flash OTA (subsequent updates, after WiFi is configured)
esphome run tubtron.yaml --device tubtron.local
```

### Minimal ESPHome YAML Structure

```yaml
esphome:
  name: tubtron
  friendly_name: Tubtron
  min_version: "2026.2.0"

esp32:
  variant: esp32
  # framework defaults to esp-idf in 2026.2.x

external_components:
  - source:
      type: local
      path: components

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  ap:
    ssid: "Tubtron Fallback"
    password: !secret fallback_password

api:
  encryption:
    key: !secret api_key

ota:
  - platform: esphome
    password: !secret ota_password

logger:
  level: DEBUG  # reduce to WARN for production

output:
  - platform: gpio
    id: temp_up_relay
    pin: GPIO16

  - platform: gpio
    id: temp_down_relay
    pin: GPIO17

climate:
  - platform: tubtron
    name: "Hot Tub"
    temp_up_output: temp_up_relay
    temp_down_output: temp_down_relay
    min_temperature: 80
    max_temperature: 104
    temperature_step: 1
```

### External Component Structure

```
tubtron/
  tubtron.yaml              # Main ESPHome config
  secrets.yaml              # WiFi, API key, OTA password (gitignored)
  components/
    tubtron/
      __init__.py            # CONFIG_SCHEMA, to_code()
      climate.py             # Climate platform registration
      tubtron_climate.h      # C++ class declaration
      tubtron_climate.cpp    # C++ implementation
```

### Home Assistant

No installation needed beyond standard ESPHome integration. ESPHome devices auto-discover via mDNS when on the same network.

## GPIO Pin Allocation

Based on ESP32 WROOM-32 capabilities and circuit design:

| GPIO | Function | Notes |
|------|----------|-------|
| GPIO16 | Temp Up photorelay | Via 680R to AQY212EH LED+. Drives Pin 2 of RJ45. |
| GPIO17 | Temp Down photorelay | Via 680R to AQY212EH LED+. Drives Pin 8 of RJ45. |
| GPIO18 | Lights photorelay (optional) | Via 680R to AQY212EH LED+. Drives Pin 3. |
| GPIO19 | Jets photorelay (optional) | Via 680R to AQY212EH LED+. Drives Pin 7. |
| GPIO4 | RS-485 RX (Phase 2) | UART1 RX. Connect to MAX485 RO pin for display reading. |
| GPIO5 | RS-485 Clock In (Phase 2) | GPIO interrupt input for synchronous clock from Pin 6. |
| GPIO2 | Onboard LED | Status indicator. Connected to blue LED on devkit. |

**Avoid:** GPIO34-39 (input-only, no output capability). GPIO0, GPIO12, GPIO15 (boot-sensitive strapping pins).

## Version Pinning Strategy

ESPHome follows calendar versioning (YYYY.M.0). Pin to the major version in `esphome:` config via `min_version` but do NOT pin to patch level -- let OTA pick up bugfixes.

```yaml
esphome:
  name: tubtron
  min_version: "2026.2.0"
```

## Sources

- ESPHome ESP32 Platform docs: https://esphome.io/components/esp32/
- ESPHome Climate Component: https://esphome.io/components/climate/
- ESPHome External Components: https://esphome.io/components/external_components/
- ESPHome GPIO Output: https://esphome.io/components/output/gpio/
- ESPHome Output Button: https://esphome.io/components/button/output/
- ESPHome Template Number: https://esphome.io/components/number/template/
- ESPHome Actions/Automations: https://esphome.io/automations/actions/
- ESPHome Security Best Practices: https://esphome.io/guides/security_best_practices/
- ESPHome Globals (restore_value): https://esphome.io/components/globals/
- ESPHome 2026.1.0 Changelog (ESP-IDF default): https://esphome.io/changelog/2026.1.0/
- ESPHome 2026.2.0 Changelog (compile improvements): https://esphome.io/changelog/2026.2.0/
- Custom components deprecation: https://developers.esphome.io/blog/2025/02/19/about-the-removal-of-support-for-custom-components/
- External component structure: https://developers.esphome.io/architecture/components/
- ESP-IDF GPIO interrupts: https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/gpio.html
- MagnusPer/Balboa-GS510SZ (reference): https://github.com/MagnusPer/Balboa-GS510SZ
- Ylianst/ESP-IQ2020 (ESPHome spa reference): https://github.com/Ylianst/ESP-IQ2020
- HA Climate integration: https://www.home-assistant.io/integrations/climate/
- HA 2026.3 release: https://www.home-assistant.io/blog/2026/03/04/release-20263/
