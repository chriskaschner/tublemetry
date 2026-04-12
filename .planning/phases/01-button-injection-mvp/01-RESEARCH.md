# Phase 1: RS-485 Display Reading - Research

**Researched:** 2026-03-13
**Domain:** RS-485 display stream decoding, ESPHome external component development, ESP32 dual-UART configuration
**Confidence:** MEDIUM (protocol partially reverse-engineered; encoding ambiguity requires physical capture to resolve)

## Summary

Phase 1 requires decoding the Balboa VS300FL4's RS-485 display stream and surfacing the current water temperature as a read-only climate entity in Home Assistant. The VS300FL4 uses a proprietary synchronous display protocol over two RS-485 channels (Pin 5 for segment data, Pin 6 for digit select/refresh) at 115200 baud 8N1. This is NOT the standard BWA 0x7E-framed protocol and NOT the GPIO-level synchronous protocol used by GS510SZ/GS523DZ boards. No published automation exists for VS-series boards.

The critical blocker is the 7-segment encoding ambiguity: only two data points exist (byte values 0x30 and 0xE6 at unknown temperatures), yielding 72 candidate bit-to-segment mappings. A temperature ladder capture at 5+ known temperatures will collapse this to a single solution. The MagnusPer/Balboa-GS510SZ project provides the closest reference for segment encoding (confirmed: 0x30="1", 0x70="7" match), but the VS300FL4 sends segment data over UART rather than GPIO, and may use a different bit ordering for some bytes.

The firmware should be an ESPHome external component using dual UARTs (UART1 for Pin 5, UART2 for Pin 6) connected via two MAX485 modules in receive-only mode. The ESP32 decodes every frame but only publishes state changes to HA, implementing the "dumb decoder" architecture where all interpretation logic lives in HA template sensors and automations.

**Primary recommendation:** Capture the temperature ladder first (physical tub task), then build the ESPHome external component with a verified lookup table. Do not attempt to ship firmware with an unverified 7-segment mapping.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Full display mirror -- decode everything the panel shows, not just temperature
- Decode temperature, OH, ICE, filter, heating indicators, lights, all 7-segment states
- Two MAX485 modules on one ESP32 (UART1 + UART2), reading Pin 5 and Pin 6 simultaneously
- ESP32 has 3 hardware UARTs; UART0 for USB logging, UART1 for Pin 5, UART2 for Pin 6
- ESP32 is a faithful decoder only -- mirrors display state to HA with zero business logic (dumb decoder)
- All interpretation, filtering, and automation logic lives in HA (template sensors, automations)
- No suppression, no "is this a setpoint flash" logic on the firmware side
- If the display shows it, HA knows it -- no information loss
- Primary: read-only climate entity (climate.hot_tub) showing current_temperature
- Setpoint controls visible but non-functional until Phase 2
- Diagnostic sensors: raw hex bytes, display state, individual digit values, decode confidence, last update timestamp
- Report both assembled display string ("104", "OH", "--") and per-digit breakdown as attributes
- Update HA on change only -- ESP32 decodes every frame internally (~60Hz), only pushes when value changes
- Non-temperature displays: keep last known temperature as current_temperature, set display_state attribute
- Setpoint flashes reported faithfully

### Claude's Discretion
- Specific GPIO pin assignments for UART1/UART2
- ESPHome component structure (custom component vs. external component vs. lambda)
- Diagnostic sensor naming conventions
- Frame parsing implementation details

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DISP-01 | ESP32 decodes RS-485 display stream to read current water temperature | Temperature ladder capture resolves encoding ambiguity; ESPHome external component with dual UART reads Pin 5 + Pin 6; frame parser extracts 7-segment bytes and decodes via lookup table |
| DISP-02 | Current temperature populates HA climate entity (full thermostat card with current + target) | ESPHome Climate class exposes current_temperature (read-only from display) and target_temperature (non-functional until Phase 2); ClimateTraits configured for HEAT mode only; publish_state() on value change |
</phase_requirements>

## Standard Stack

### Core
| Library/Tool | Version | Purpose | Why Standard |
|-------------|---------|---------|--------------|
| ESPHome | 2025.x+ | Firmware framework | Native HA integration, OTA, YAML config, external component support |
| ESP-IDF UART | (bundled) | Hardware UART driver | ESP32 has 3 hardware UARTs; ESPHome wraps ESP-IDF UART for reliable 115200 baud |
| MAX485 module | - | RS-485 to TTL level conversion | 12k ohm input impedance, receive-only mode (RE=LOW, DE=LOW), standard for passive bus tap |
| PulseView/sigrok | latest | Logic analyzer capture | Used with Lonely Binary 8ch analyzer for temperature ladder capture |

### Supporting
| Library/Tool | Version | Purpose | When to Use |
|-------------|---------|---------|-------------|
| Python (uv) | 3.12+ | Capture analysis scripts | Temperature ladder data processing, lookup table generation |
| pytest | latest | Test decode logic | Unit test the 7-segment lookup table and frame parser in Python before porting to C++ |
| Home Assistant template sensors | - | HA-side interpretation | Template sensors derive meaningful states from raw diagnostic data |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| ESPHome external component | Arduino sketch + MQTT | Loses native HA integration, OTA, YAML config; more code to maintain |
| Dual MAX485 modules | Single MAX485 + software demux | Pin 5 and Pin 6 are independent RS-485 channels; need two physical transceivers |
| Python for capture analysis | C++ on ESP32 | Python is better for exploratory analysis; C++ lookup table is trivial once mapping is known |

### Installation
```bash
# Python analysis environment
uv init tubtron-analysis
uv add pyserial numpy pytest

# ESPHome (via HA addon or pip)
pip install esphome
```

## Architecture Patterns

### Recommended Project Structure
```
tubtron/
├── esphome/
│   ├── tubtron.yaml                 # Main ESPHome config
│   └── components/
│       └── tubtron_display/
│           ├── __init__.py          # ESPHome Python config schema
│           ├── climate.py           # Climate platform registration
│           ├── sensor.py            # Diagnostic sensor registration
│           ├── text_sensor.py       # Text sensor registration
│           ├── tubtron_display.h    # C++ header (component class)
│           └── tubtron_display.cpp  # C++ implementation (frame parser, decoder)
├── 485/
│   ├── scripts/                     # Existing analysis scripts
│   ├── captures/                    # Temperature ladder capture files
│   └── lookup_table.py             # Generated/verified 7-segment mapping
├── tests/
│   ├── test_decode.py              # Unit tests for 7-segment decoding
│   ├── test_frame_parser.py        # Unit tests for frame parsing
│   └── test_display_state.py       # Unit tests for display state machine
└── reference/
    └── status_03_08.md             # Protocol analysis notes
```

### Pattern 1: ESPHome External Component (Recommended over lambda or custom component)
**What:** A proper external component with Python config validation and C++ implementation, registered as a Climate platform and sensor platforms.
**When to use:** Always for this project -- external components are the modern ESPHome pattern; custom components are deprecated.
**Why:** External components provide YAML schema validation, proper lifecycle management (setup/loop), and clean separation of config from implementation. They survive ESPHome upgrades.

```yaml
# tubtron.yaml
external_components:
  - source:
      type: local
      path: components

uart:
  - id: uart_pin5
    rx_pin: GPIO16
    baud_rate: 115200
    data_bits: 8
    parity: NONE
    stop_bits: 1

  - id: uart_pin6
    rx_pin: GPIO17
    baud_rate: 115200
    data_bits: 8
    parity: NONE
    stop_bits: 1

climate:
  - platform: tubtron_display
    name: "Hot Tub"
    id: hot_tub
    uart_pin5: uart_pin5
    uart_pin6: uart_pin6

sensor:
  - platform: tubtron_display
    tubtron_id: hot_tub
    decode_confidence:
      name: "Hot Tub Decode Confidence"
      entity_category: "diagnostic"

text_sensor:
  - platform: tubtron_display
    tubtron_id: hot_tub
    display_string:
      name: "Hot Tub Display"
      entity_category: "diagnostic"
    raw_hex:
      name: "Hot Tub Raw Hex"
      entity_category: "diagnostic"
    display_state:
      name: "Hot Tub Display State"
      entity_category: "diagnostic"
```

### Pattern 2: Dumb Decoder (Firmware Architecture)
**What:** ESP32 faithfully mirrors every display state to HA with zero interpretation. All business logic lives in HA.
**When to use:** Always -- this is the locked architectural decision.
**Why:** Business logic mistakes are fixable in HA YAML without reflashing firmware. No information loss. The firmware is a transparent bridge.

```cpp
// C++ pseudocode for the dumb decoder pattern
class TubtronDisplay : public climate::Climate, public Component, public uart::UARTDevice {
 public:
  void setup() override;
  void loop() override;
  climate::ClimateTraits traits() override;
  void control(const climate::ClimateCall &call) override;

 private:
  // Frame parsing
  void process_pin5_frame(const uint8_t *data, size_t len);
  void process_pin6_frame(const uint8_t *data, size_t len);
  char decode_7seg(uint8_t byte_val);

  // State tracking (publish only on change)
  float last_temperature_{NAN};
  std::string last_display_string_;
  std::string last_display_state_;

  // Diagnostic sensors (set by parent component, published by sensor sub-components)
  sensor::Sensor *decode_confidence_sensor_{nullptr};
  text_sensor::TextSensor *display_string_sensor_{nullptr};
  text_sensor::TextSensor *raw_hex_sensor_{nullptr};
  text_sensor::TextSensor *display_state_sensor_{nullptr};
};
```

### Pattern 3: Temperature Persistence During Non-Temperature Displays
**What:** When display shows OH, ICE, "--", or setpoint flash, keep the last known valid temperature as `current_temperature` and update `display_state` attribute.
**When to use:** Whenever the decoded display string is not a valid temperature.
**Why:** Prevents gaps in HA temperature history graphs. HA automations can check `display_state` for edge cases.

```cpp
void TubtronDisplay::update_temperature(const std::string &display_str) {
  // Try to parse as temperature (2 or 3 digit number)
  // If valid: update current_temperature AND display_state = "temperature"
  // If not valid (OH, ICE, --, etc): keep current_temperature, update display_state only
  if (is_valid_temperature(display_str)) {
    float temp = parse_temperature(display_str);
    if (temp != this->last_temperature_) {
      this->current_temperature = temp;
      this->last_temperature_ = temp;
      this->publish_state();
    }
    this->set_display_state("temperature");
  } else {
    this->set_display_state(display_str);  // "OH", "ICE", "--", etc.
    // current_temperature unchanged -- last valid reading persists
  }
}
```

### Anti-Patterns to Avoid
- **Interpreting setpoint flashes on the ESP32:** The firmware should report what the display shows. HA decides if a 3-second "103" flash after a button press is a setpoint or a temperature reading. This is the dumb decoder principle.
- **Polling UART instead of reading in loop:** At 115200 baud with ~60Hz frame rate, data arrives continuously. Read available bytes every loop() iteration and buffer into frames. Do not use timers or delays.
- **Publishing every frame to HA:** At 60Hz, this would flood the HA API. Only publish when decoded values change. The ESP32 should track the previous state and suppress duplicate publishes.
- **Using ESPHome's deprecated custom_component:** Use external_components with proper Python/C++ structure. Custom components are officially deprecated.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| UART byte reading | Manual register manipulation | ESPHome UARTDevice base class | Handles buffering, pin config, baud rate. Provides `available()`, `read_byte()`, `read_array()` |
| Climate entity | Raw MQTT publishing | ESPHome Climate base class | Provides `current_temperature`, `publish_state()`, HA auto-discovery, proper entity lifecycle |
| Diagnostic sensors | Custom MQTT topics | ESPHome Sensor/TextSensor with `entity_category: diagnostic` | Auto-discovery, proper HA integration, entity categorization |
| WiFi/OTA management | Custom networking code | ESPHome built-in `wifi:` and `ota:` | Handles reconnection, fallback AP mode, encrypted OTA, captive portal |
| 7-segment decoding | Runtime brute-force | Static lookup table (generated from ladder capture) | The 72-solution ambiguity is resolved once during capture analysis, not at runtime |

**Key insight:** The only truly custom code is the frame parser and 7-segment lookup table. Everything else -- UART, WiFi, HA integration, OTA, entity management -- is standard ESPHome infrastructure.

## Common Pitfalls

### Pitfall 1: RS-485 Line Loading Causes Display Corruption
**What goes wrong:** Connecting an RS-485 adapter (MAX485) to Pin 6 caused the physical display to show "80" flashing. The adapter loads the RS-485 line and interferes with the display refresh signal.
**Why it happens:** Each MAX485 receiver presents ~12k ohm impedance between A and B. The T-splitter + adapter creates a stub topology (not daisy-chain). Signal reflections and impedance mismatches corrupt the display multiplexing signal on Pin 6.
**How to avoid:**
1. Use the new RJ45 screw terminal breakouts (ordered) instead of T-splitter + cut cable. Shorter stubs reduce reflections.
2. For Pin 6, consider whether it's even needed: Pin 5 alone may carry sufficient information (digit select pattern on Pin 6 appears constant). Test with Pin 5 only first.
3. If Pin 6 is needed, try a high-impedance buffer (74HC125) between the bus and MAX485 to reduce loading.
4. Keep connection wires as short as possible (under 10cm).
**Warning signs:** Display shows wrong digits, flashes unexpectedly, or shows "80" when it shouldn't.

### Pitfall 2: Frame Boundary Detection in UART Stream
**What goes wrong:** UART delivers a continuous byte stream. Without explicit frame delimiters (no 0x7E framing), the parser can misalign and decode garbage.
**Why it happens:** The VS300FL4 protocol sends 8-byte frames on Pin 5 at ~60Hz with ~110ms gaps, but the ESP32's UART buffer accumulates bytes without preserving timing boundaries.
**How to avoid:**
1. Use UART idle detection: if no bytes arrive for >1ms (at 115200 baud, one byte takes ~87us), treat it as a frame boundary.
2. Look for the FE marker byte as frame start (present in idle frames, absent during lights-on). Use FE as a sync byte with fallback to timing.
3. Validate frame length (expect 7-8 bytes per frame on Pin 5).
4. Implement a ring buffer that aligns to frame boundaries.
**Warning signs:** Decoded values jump erratically, display_string contains impossible combinations.

### Pitfall 3: Unverified 7-Segment Mapping Deployed to Production
**What goes wrong:** Deploying firmware with an assumed encoding table that maps bytes to wrong digits. Temperature reads 95 when it's actually 104.
**Why it happens:** 72 candidate solutions exist with only 2 data points. The brute-force scripts show temperature pairs like (81,82), (81,85), (91,95) are all valid under different mappings.
**How to avoid:** Temperature ladder capture at 5+ known temperatures before writing the final lookup table. Each additional data point eliminates candidate solutions exponentially.
**Warning signs:** This pitfall is silent -- wrong temperatures look plausible. Verify by cross-checking the firmware reading against the physical panel display.

### Pitfall 4: ESP32 UART1 Default Pins Conflict with Flash
**What goes wrong:** ESP32 UART1 defaults to GPIO9/GPIO10, which are connected to the SPI flash on most modules. Using these pins crashes the ESP32.
**Why it happens:** ESP32 hardware UART controllers are flexible (any GPIO), but the defaults for UART1 are on flash-connected pins.
**How to avoid:** Always explicitly set `rx_pin` and `tx_pin` in the ESPHome UART config. Use GPIO16 for UART1 RX and GPIO17 for UART2 RX (safe, available pins on WROOM-32). TX pins are not needed (receive-only), but ESPHome may require them -- use unused GPIOs or set to a safe pin.
**Warning signs:** ESP32 boot loops, crashes on UART init, brownout resets.

### Pitfall 5: Climate Entity Shows NaN Before First Valid Reading
**What goes wrong:** On boot, `current_temperature` is NaN until the first valid frame is decoded. HA shows "Unknown" in the thermostat card.
**Why it happens:** ESPHome Climate initializes temperature to NaN. Until the ESP32 receives and decodes a valid frame from the tub, there's no temperature to report.
**How to avoid:** Accept the initial NaN gracefully. Do not publish a fake temperature. The first valid reading typically arrives within 1-2 seconds of boot (frames come at 60Hz). Optionally, save last known temperature to flash (ESP32 preferences) and restore on boot, but mark as stale via a diagnostic sensor.
**Warning signs:** HA thermostat card shows "Unknown" for extended periods after reboot.

## Code Examples

### 7-Segment Lookup Table (GS510SZ Reference, needs verification via ladder capture)
```cpp
// Source: MagnusPer/Balboa-GS510SZ Balboa_GS_Interface.cpp
// IMPORTANT: This is the GS510SZ encoding. VS300FL4 may differ.
// Verify with temperature ladder capture before using.
// Bit layout: bit7=dp, bits6-0 = segments a-g (GS510SZ convention)
// 0x30 = "1" CONFIRMED for VS300FL4
// 0x70 = "7" CONFIRMED for VS300FL4
// All other mappings need verification

static const char SEVEN_SEG_TABLE[] = {
  // Index by (byte_value & 0x7F) -- mask off dp bit
  // Build from verified ladder capture data
};

char decode_7seg(uint8_t byte_val) {
  uint8_t segments = byte_val & 0x7F;  // mask off dp (bit 7)
  bool dp = byte_val & 0x80;
  // Lookup in verified table
  // Return digit character or '?' for unknown patterns
}
```

### ESPHome Climate Entity (Read-Only)
```cpp
// Source: ESPHome API docs -- climate::Climate class
// https://api-docs.esphome.io/classesphome_1_1climate_1_1_climate

climate::ClimateTraits TubtronDisplay::traits() {
  auto traits = climate::ClimateTraits();
  traits.set_supports_current_temperature(true);
  traits.set_supported_modes({climate::CLIMATE_MODE_HEAT});
  traits.set_visual_min_temperature(80.0f);
  traits.set_visual_max_temperature(104.0f);
  traits.set_visual_temperature_step(1.0f);
  return traits;
}

void TubtronDisplay::control(const climate::ClimateCall &call) {
  // Phase 1: read-only, ignore all control requests
  // Phase 2 will implement button injection here
}
```

### Dual UART Configuration
```yaml
# Source: ESPHome UART docs -- https://esphome.io/components/uart/
# ESP32 WROOM-32 has 3 hardware UARTs
# UART0: reserved for USB logging
# UART1: Pin 5 (display content)
# UART2: Pin 6 (display refresh)

uart:
  - id: uart_pin5
    rx_pin: GPIO16    # Connect to MAX485 #1 RO pin
    tx_pin: GPIO04    # Not used for receive-only, but ESPHome may require it
    baud_rate: 115200
    data_bits: 8
    parity: NONE
    stop_bits: 1

  - id: uart_pin6
    rx_pin: GPIO17    # Connect to MAX485 #2 RO pin
    tx_pin: GPIO05    # Not used for receive-only
    baud_rate: 115200
    data_bits: 8
    parity: NONE
    stop_bits: 1
```

### MAX485 Receive-Only Wiring
```
RJ45 Pin 5 (Blue/White) ─── A ┐
                                 MAX485 #1 ─── RO ──> ESP32 GPIO16 (UART1 RX)
RJ45 Pin 4 (Blue/GND)   ─── B ┘
                               ├── RE ──> GND (always receive)
                               ├── DE ──> GND (never transmit)
                               ├── VCC ──> 3.3V
                               └── GND ──> ESP32 GND

RJ45 Pin 6 (Green)      ─── A ┐
                                 MAX485 #2 ─── RO ──> ESP32 GPIO17 (UART2 RX)
RJ45 Pin 4 (Blue/GND)   ─── B ┘
                               ├── RE ──> GND (always receive)
                               ├── DE ──> GND (never transmit)
                               ├── VCC ──> 3.3V
                               └── GND ──> ESP32 GND

Note: MAX485 can operate at 3.3V or 5V. At 3.3V, input threshold
may be marginal for 5V RS-485 signals. Test at 3.3V first; if
unreliable, power MAX485 at 5V and add a voltage divider on RO
(5V -> 3.3V) before connecting to ESP32 GPIO.
```

### Frame Parser Skeleton
```cpp
// Parse Pin 5 display content stream
// Known idle frame: FE 06 70 XX 00 06 70 00 (8 bytes)
// Sub-frame model: [byte0 byte1 byte2 byte3] [byte4 byte5 byte6 byte7]

void TubtronDisplay::process_pin5_data() {
  while (this->pin5_uart_->available()) {
    uint8_t byte;
    this->pin5_uart_->read_byte(&byte);
    this->pin5_buffer_[this->pin5_index_++] = byte;

    // Frame boundary detection via timing
    uint32_t now = micros();
    if (now - this->pin5_last_byte_time_ > 1000) {  // >1ms gap = new frame
      this->pin5_index_ = 0;
    }
    this->pin5_last_byte_time_ = now;

    // Process complete frame
    if (this->pin5_index_ >= 8) {
      this->decode_pin5_frame(this->pin5_buffer_, 8);
      this->pin5_index_ = 0;
    }
  }
}

void TubtronDisplay::decode_pin5_frame(const uint8_t *frame, size_t len) {
  // Sub-frame 1: bytes 0-3
  char d0 = decode_7seg(frame[0]);
  char d1 = decode_7seg(frame[1]);
  char d2 = decode_7seg(frame[2]);
  char d3 = decode_7seg(frame[3]);

  // Assemble display string
  std::string display_str;
  display_str += d0;
  display_str += d1;
  display_str += d2;
  display_str += d3;

  // Check for status byte (FE present/absent)
  bool has_fe = (frame[0] == 0xFE);

  // Update state if changed
  if (display_str != this->last_display_string_) {
    this->last_display_string_ = display_str;
    this->update_temperature(display_str);
    // Update diagnostic sensors...
  }
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| ESPHome custom_component | External components (`external_components:`) | ESPHome 2021.10+ | Custom components deprecated; external components have proper Python schema validation and C++ lifecycle |
| `std::string` for custom fan/preset modes | `const char*` flash storage | ESPHome 2025.11 | Climate entity API changed; use string literals for custom modes, not heap strings |
| Direct member assignment for custom modes | Protected setter methods | ESPHome 2025.11 | `this->custom_fan_mode = "X"` no longer compiles; use `this->set_custom_fan_mode_("X")` |
| GPIO-level synchronous read (GS510SZ) | UART-level read (VS300FL4) | N/A (different hardware) | VS300FL4 sends display data as RS-485 UART bytes, not GPIO clock+data. Fundamentally different interface |

**Deprecated/outdated:**
- ESPHome `custom_component:` YAML key -- replaced by `external_components:`
- MagnusPer's GPIO interrupt approach -- works for GS510SZ (clock+data on GPIO), does NOT apply to VS300FL4 (data arrives as UART bytes on RS-485)

## VS300FL4 Protocol vs. Known Balboa Protocols

| Property | BWA (BP-series) | GS510SZ (GS-series) | VS300FL4 (VS-series) |
|----------|-----------------|---------------------|---------------------|
| Transport | RS-485, 115200 8N1 | GPIO synchronous clock+data | RS-485, 115200 8N1 |
| Framing | 0x7E delimited | 42 clock pulses per cycle | No delimiter; 8-byte frames with timing gaps |
| Display data | Structured messages | 39 bits (7 bits x 6 chunks) | 8 bytes on Pin 5 (7-seg encoded) |
| Panel type | TP-series (smart, has MCU) | VL-series (dumb, no MCU) | VL-series (dumb, no MCU) |
| Button channel | RS-485 bidirectional | GPIO (3 clock pulses) | Analog voltage (separate pins) |
| Published automation | Yes (multiple projects) | Yes (MagnusPer) | No (this is first) |
| 7-seg encoding | N/A (messages carry values) | bit7=dp, bits6-0=a-g | Unknown (partially confirmed matches GS510SZ) |

## Known Protocol Details (VS300FL4)

### Pin 5 -- Display Content Stream
- **Baud:** 115200 8N1
- **Frame structure:** 8 bytes repeating at ~60Hz
- **Idle frame:** `FE 06 70 XX 00 06 70 00`
  - Byte 3 (XX) varies with temperature
  - Sub-frame model: bytes [0-3] and [4-7] may represent two display zones
  - `FE` byte is a status indicator (present during idle, absent when lights are on)
- **Button-press frames:** Different structure during temp changes
  - Temp down: `06 70 E6 00 | 00 06 00 F3` + burst `E6 77 E6 E6 77 E6 E6 77 E6 E0 FF`
  - Temp up: `06 70 E6 00 | 00 03 18 00` + same burst

### Pin 6 -- Display Refresh Stream
- **Baud:** 115200 8N1
- **Frame structure:** `77 E6 E6` repeating (10 bytes with FF terminator)
- **Behavior:** Constant pattern, no variation on button presses
- **Note:** This channel is more sensitive to line loading (caused display corruption in prior testing)

### Confirmed Byte-to-Digit Mappings (from GS510SZ cross-reference)
| Byte | Digit | Confidence |
|------|-------|-----------|
| 0x30 | "1" | HIGH -- confirmed by both GS510SZ reference and project captures |
| 0x70 | "7" | HIGH -- confirmed by both GS510SZ reference and project captures |
| 0x00 | " " (blank) | HIGH -- 0 segments lit = blank |
| 0xFE | "8" or indicator | MEDIUM -- if dp is bit 7, 0x7E = all segments = "8"; but FE may be a frame marker |
| 0xE6 | unknown digit | LOW -- 72 candidate mappings; needs ladder capture |
| 0x06 | unknown | LOW -- could be "1" variant or segment subset |

## Open Questions

1. **Pin 6 necessity**
   - What we know: Pin 6 carries a constant refresh pattern (77 E6 E6 repeating). It showed no variation on button presses. Connecting to it caused display corruption.
   - What's unclear: Whether Pin 6 data is needed for display decoding, or if Pin 5 alone contains all display information.
   - Recommendation: Start with Pin 5 only. If Pin 5 alone resolves temperature + display state, skip Pin 6 entirely. Add Pin 6 only if there are display states that Pin 5 cannot distinguish alone.

2. **FE byte semantics**
   - What we know: Present in idle frame (byte 0), absent when lights are toggled. Could be a frame sync marker or the first display digit.
   - What's unclear: Whether FE is part of the display data (encoding digit "8" or all segments) or a control/sync byte.
   - Recommendation: Temperature ladder capture will clarify -- if byte 0 changes with temperature, it's display data. If constant (always FE when idle), it's a control byte.

3. **MAX485 at 3.3V vs 5V**
   - What we know: The RS-485 bus runs at 5V levels (from the Balboa board's +5V supply on Pin 1). MAX485 modules work at both 3.3V and 5V.
   - What's unclear: Whether 3.3V-powered MAX485 reliably reads 5V RS-485 differential signals. The RS-485 standard specifies +/-200mV threshold, but common-mode voltage range matters.
   - Recommendation: Test with 3.3V first (simplest). If unreliable, power MAX485 at 5V and add a 5V-to-3.3V voltage divider on the RO output before connecting to ESP32 GPIO.

4. **Frame timing vs byte-count parsing**
   - What we know: Frames are 8 bytes (idle) or 7 bytes (lights-on) or 10-11 bytes (burst during button press). No framing bytes.
   - What's unclear: Whether UART inter-frame gap is consistent enough for reliable frame boundary detection.
   - Recommendation: Use both timing AND pattern matching. Detect gaps >1ms as frame boundaries (one byte at 115200 = 87us). Cross-validate with FE byte position and frame length.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (Python, managed via uv) |
| Config file | none -- Wave 0 creates pyproject.toml with pytest config |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DISP-01 | 7-segment byte decodes to correct digit | unit | `uv run pytest tests/test_decode.py::test_7seg_lookup -x` | -- Wave 0 |
| DISP-01 | 8-byte frame parses to display string | unit | `uv run pytest tests/test_frame_parser.py::test_idle_frame -x` | -- Wave 0 |
| DISP-01 | Non-temperature displays (OH, ICE, --) detected | unit | `uv run pytest tests/test_display_state.py::test_non_temp_states -x` | -- Wave 0 |
| DISP-01 | Temperature persistence during non-temp display | unit | `uv run pytest tests/test_display_state.py::test_temp_persistence -x` | -- Wave 0 |
| DISP-02 | Climate entity reports correct temperature | integration | Manual -- flash ESP32, verify HA entity shows correct temp | N/A |
| DISP-02 | Diagnostic sensors populate in HA | integration | Manual -- verify entity_category: diagnostic sensors appear | N/A |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green + manual verification against physical display

### Wave 0 Gaps
- [ ] `pyproject.toml` -- project config with pytest dependency
- [ ] `tests/test_decode.py` -- 7-segment lookup table tests (parameterized by ladder capture data)
- [ ] `tests/test_frame_parser.py` -- frame parsing tests with known byte sequences
- [ ] `tests/test_display_state.py` -- display state machine tests (temperature persistence, edge states)
- [ ] `tests/conftest.py` -- shared fixtures (sample frames, expected decode results)
- [ ] Framework install: `uv add --dev pytest`

**Note:** The decode logic should be developed and tested in Python first (matching user's preferred tooling), then ported to C++ for the ESPHome component. The Python tests validate the algorithm; the C++ port is a mechanical translation. Hardware integration testing (DISP-02) requires flashing the ESP32 and is manual by nature.

## Sources

### Primary (HIGH confidence)
- [MagnusPer/Balboa-GS510SZ](https://github.com/MagnusPer/Balboa-GS510SZ) -- 7-segment encoding table, synchronous protocol reference, closest match to VS300FL4
- [ESPHome UART docs](https://esphome.io/components/uart/) -- dual UART configuration on ESP32
- [ESPHome External Components](https://esphome.io/components/external_components/) -- component structure, YAML config
- [ESPHome Climate API](https://api-docs.esphome.io/classesphome_1_1climate_1_1_climate) -- Climate class, ClimateTraits, publish_state()
- [ESPHome Climate Component](https://esphome.io/components/climate/) -- YAML config, visual settings, read-only patterns
- Project captures and analysis scripts in `485/` directory -- confirmed protocol parameters

### Secondary (MEDIUM confidence)
- [Shuraxxx/Balboa-GS523DZ-VL801D](https://github.com/Shuraxxx/-Balboa-GS523DZ-with-panel-VL801D-DeluxeSerie--MQTT) -- VL-series panel encoding (GS523DZ variant), similar BCD-to-7-segment approach
- [netmindz/balboa_GL_ML_spa_control](https://github.com/netmindz/balboa_GL_ML_spa_control) -- GL/ML protocol reference (different from VS-series but shares connector architecture)
- [geoffdavis/esphome-mitsubishiheatpump](https://github.com/geoffdavis/esphome-mitsubishiheatpump) -- reference ESPHome external component with UART-based climate entity
- [MAX485 datasheet](https://www.analog.com/MAX481/datasheet) -- 12k ohm receiver input impedance, receive-only mode (RE=LOW, DE=LOW)

### Tertiary (LOW confidence)
- [ESPHome Developer Documentation](https://developers.esphome.io/) -- component writing guide (404 at time of research, may have moved)
- Community forum patterns for UART custom components -- code patterns verified against official API docs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- ESPHome + ESP32 + MAX485 is the established pattern for RS-485 HA integration
- Architecture: HIGH -- dumb decoder is a locked decision; external component pattern is well-documented
- Protocol details: MEDIUM -- frame structure confirmed from captures, but 7-segment encoding has 72 ambiguous solutions
- Pitfalls: HIGH -- line loading issue observed firsthand; UART pin conflicts well-documented in ESP32 community
- Test approach: MEDIUM -- Python unit tests for decode logic is solid; hardware integration testing is inherently manual

**Research date:** 2026-03-13
**Valid until:** 2026-04-13 (stable domain -- protocol won't change; ESPHome API changes are the main risk)
