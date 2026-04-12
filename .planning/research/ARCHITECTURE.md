# Architecture Patterns

**Domain:** ESP32-based hot tub automation with button injection, RS-485 display reading, and Home Assistant integration
**Researched:** 2026-03-13

## Recommended Architecture

The system is a **bridge architecture**: an ESP32 running ESPHome sits between the Balboa VS300FL4 control board and Home Assistant, translating HA climate commands into analog button presses (write path) and RS-485 display data into temperature readings (read path). The hot tub board remains unmodified -- the ESP32 is a passive tap with isolated injection capability.

```
+-------------------+       WiFi/API        +-------------------+
|  Home Assistant   | <-------------------> |    ESP32 + ESPHome |
|  (climate entity) |                       |    (bridge node)   |
+-------------------+                       +--------+----------+
                                                     |
                              +----------------------+----------------------+
                              |                                             |
                     GPIO + Photorelay                              UART + MAX485
                     (write path)                                   (read path)
                              |                                             |
                     +--------v----------+                         +--------v----------+
                     | RJ45 Button Pins  |                         | RJ45 RS-485 Pins  |
                     | Pin 2: Temp Up    |                         | Pin 5: Display Data|
                     | Pin 8: Temp Down  |                         | Pin 6: Display Clk |
                     | Pin 3: Lights     |                         +--------------------+
                     | Pin 7: Jets       |                                    |
                     +-------------------+                         +----------v---------+
                              |                                    | VS300FL4 Board     |
                              +------>  VS300FL4 Board  <----------+ (sends display     |
                                        (reads ADC)                |  data to panel)    |
                                                                   +--------------------+
```

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| **Home Assistant** | User interface, TOU automation scheduling, climate entity display | ESPHome via native API over WiFi |
| **ESPHome Firmware** | Climate entity logic, button press sequencing, re-home algorithm, temperature state management | HA (API), GPIO outputs (photorelays), UART (MAX485) |
| **GPIO Output Layer** | Momentary pulse generation for button simulation via photorelays | ESPHome firmware (receives commands), RJ45 button pins (drives analog lines) |
| **RS-485 Read Layer** | Receive and decode synchronous display stream from board | ESPHome firmware (provides decoded temperature), MAX485 transceiver, RJ45 pins 5/6 |
| **Photorelay Circuit** | Galvanic isolation between ESP32 3.3V domain and hot tub 5V analog domain | GPIO output (LED side), RJ45 button pins (switch side) |
| **MAX485 Transceiver** | Level shifting and RS-485 bus interface for reading display stream | ESP32 UART RX, RJ45 pins 5/6 |
| **VS300FL4 Board** | Hot tub control -- heater, pump, display. Completely unmodified. | Panel (RJ45), ESP32 tap (passive) |
| **VL-series Panel** | Physical buttons and 7-segment display. Stays connected, undisturbed. | VS300FL4 board (RJ45) |

### Data Flow

**Command Path (Home Assistant to Hot Tub):**

1. HA automation calls `climate.set_temperature` with target (e.g., 104F)
2. ESPHome climate entity receives target via native API
3. Climate component calculates press count: `abs(target - current_setpoint)` presses of Temp Up or Temp Down
4. **Re-home strategy** (if no verified current setpoint): slam 25x Temp Down to guaranteed floor (80F), then count up to target
5. For each press: GPIO HIGH (680ms typical) -> photorelay closes -> +5V bridges to button pin -> board reads ADC spike -> GPIO LOW
6. Inter-press delay (empirically determined, ~300-500ms expected) between each press
7. ESPHome updates internal setpoint state after sequence completes

**Status Path (Hot Tub to Home Assistant):**

Phase 1 (open-loop): No read path. ESPHome tracks setpoint via internal counter only.

Phase 2 (closed-loop):
1. VS300FL4 board sends 7-segment display data on Pin 5 at 60Hz, clocked by Pin 6
2. MAX485 transceiver converts RS-485 differential to TTL for ESP32 UART RX
3. ESPHome custom component decodes 8-byte frames, extracts temperature-dependent byte (position 3)
4. 7-segment lookup table maps byte value to display digit
5. Decoded temperature published as `current_temperature` on the climate entity
6. HA displays actual temperature alongside setpoint

**Automation Path (TOU Schedule):**

1. HA time-based automation triggers at schedule boundaries (e.g., weekday 10am)
2. Automation calls `climate.set_temperature` with on-peak setpoint (99F) or off-peak setpoint (104F)
3. Climate entity on ESP32 executes button press sequence (as above)
4. Optional: Phase 2 verification reads display to confirm setpoint was applied correctly

## Patterns to Follow

### Pattern 1: ESPHome External Component for Custom Climate

**What:** Implement the hot tub interface as an ESPHome external component (not deprecated "custom component"). This is a C++ class that extends `esphome::climate::Climate` and `esphome::Component`, with Python config validation in `__init__.py`.

**Why:** The brianfeucht/esphome-balboa-spa project and Ylianst/ESP-IQ2020 both use this pattern successfully. It provides native HA integration, OTA updates, and YAML configuration -- the standard approach for non-trivial ESPHome hardware integrations.

**Structure:**
```
esphome/
  tubtron.yaml              # Main ESPHome config
  components/
    tubtron/
      __init__.py            # Python: CONFIG_SCHEMA, to_code()
      climate.py             # Python: climate platform registration
      tubtron_climate.h      # C++: class declaration
      tubtron_climate.cpp    # C++: implementation
```

**When:** Use this pattern from the start. Even Phase 1 (open-loop button injection) benefits from the climate entity abstraction.

**Example (climate class skeleton):**
```cpp
// tubtron_climate.h
#pragma once
#include "esphome/components/climate/climate.h"
#include "esphome/core/component.h"
#include "esphome/components/output/binary_output.h"

namespace esphome {
namespace tubtron {

class TubtronClimate : public climate::Climate, public Component {
 public:
  void setup() override;
  void loop() override;

  climate::ClimateTraits traits() override;
  void control(const climate::ClimateCall &call) override;

  void set_temp_up_output(output::BinaryOutput *output) { temp_up_ = output; }
  void set_temp_down_output(output::BinaryOutput *output) { temp_down_ = output; }

 protected:
  void press_button_(output::BinaryOutput *button, int count);
  void rehome_and_set_(float target);

  output::BinaryOutput *temp_up_{nullptr};
  output::BinaryOutput *temp_down_{nullptr};

  float assumed_setpoint_{80.0f};  // Floor after re-home
  uint32_t press_duration_ms_{500};
  uint32_t inter_press_delay_ms_{400};
};

}  // namespace tubtron
}  // namespace esphome
```

**Confidence:** HIGH -- this is the documented ESPHome pattern for custom hardware.

### Pattern 2: GPIO Output with Momentary Pulse for Button Injection

**What:** Use ESPHome's `output::BinaryOutput` (GPIO platform) to drive photorelay LEDs. Each "button press" is a timed pulse: HIGH for press duration, LOW for inter-press gap.

**Why:** ESPHome's GPIO output component handles pin initialization, safe boot states (off), and integrates cleanly with automation sequences. The photorelay (AQY212EH) provides galvanic isolation -- the ESP32 only drives the LED input side, never touches the 5V analog lines directly.

**When:** All button injection, all phases.

**Example (YAML for GPIO outputs):**
```yaml
output:
  - platform: gpio
    id: temp_up_relay
    pin: GPIO18
    inverted: false

  - platform: gpio
    id: temp_down_relay
    pin: GPIO19
    inverted: false

  - platform: gpio
    id: lights_relay
    pin: GPIO21
    inverted: false

  - platform: gpio
    id: jets_relay
    pin: GPIO22
    inverted: false
```

**Confidence:** HIGH -- standard ESPHome GPIO pattern, well-documented.

### Pattern 3: Re-Home Strategy for Open-Loop Setpoint Control

**What:** Before setting a new target temperature, slam Temp Down 25 times to guarantee the setpoint is at the floor (80F), then press Temp Up `(target - 80)` times to reach the desired setpoint. This eliminates cumulative drift.

**Why:** Without display reading (Phase 1), the ESP32 cannot verify what temperature the tub is currently set to. Manual adjustments at the panel, missed button presses, or power cycles silently desync the internal state. Re-homing on every setpoint change is expensive (~50 presses for a 99->104 change instead of 5) but guaranteed correct.

**When:** Phase 1 (open-loop) always. Phase 2 (closed-loop) can skip re-home when display confirms current setpoint.

**Optimization:** The re-home can be optimized by holding the button -- the Balboa board auto-repeats when a button is held for >2 seconds. This needs empirical timing characterization (Phase 1 Task 3).

**Confidence:** MEDIUM -- the strategy is sound but press timing and auto-repeat behavior need empirical validation.

### Pattern 4: Phased Read Path (Phase 2 Extension)

**What:** Add RS-485 display reading as a separate component that feeds `current_temperature` into the existing climate entity. The read path is independent of the write path.

**Why:** The MagnusPer/Balboa-GS510SZ project shows that synchronous clock+data display protocols require interrupt-driven or tight-loop decoding. This is complex and should not block the functional write path. The brianfeucht/esphome-balboa-spa project demonstrates the multi-component pattern where read and write paths are loosely coupled.

**When:** Phase 2, after open-loop control is proven working.

**Architecture for read path:**
```
Pin 6 (clock) --> MAX485 --> ESP32 GPIO interrupt (rising edge)
Pin 5 (data)  --> MAX485 --> ESP32 UART RX (read on clock edge)
```

The GS510SZ reference uses 50Hz cycles with 39-bit chunks. The VS300FL4 uses 60Hz cycles with 8-byte frames. The decoding logic must handle:
- Frame synchronization (detect start of 8-byte frame)
- 7-segment byte-to-digit lookup (resolved by temperature ladder capture)
- Status flag extraction (FE byte presence, burst patterns)

**Confidence:** MEDIUM -- the general approach is validated by GS510SZ, but VS-series protocol differences mean the decoding logic is custom.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Using ESPHome's Built-in Thermostat Climate Controller

**What:** ESPHome's `thermostat` platform expects to directly control a heater relay with hysteresis, deadband, and PID-like logic.

**Why bad:** The hot tub board manages its own heating loop. The ESP32 only changes the setpoint -- it does not control the heater directly. Using the thermostat platform would fight the board's built-in control logic and add unnecessary complexity.

**Instead:** Use a bare `climate::Climate` subclass that exposes `target_temperature` and `current_temperature` without any heating/cooling control logic. The ESP32 is a remote control, not a thermostat.

### Anti-Pattern 2: Bare GPIO Without Isolation

**What:** Driving button pins directly from ESP32 GPIO (3.3V) without photorelays.

**Why bad:** The VS300FL4 button lines are sensitive analog circuits. An unterminated cable already caused phantom presses. Direct GPIO connection introduces shared ground paths, voltage mismatch (3.3V vs 5V), and EMI coupling from the ESP32's WiFi radio.

**Instead:** Always use photorelays (AQY212EH) for galvanic isolation. The LED side is on the ESP32 3.3V domain; the switch side is on the tub's 5V domain. No shared ground, no coupling.

### Anti-Pattern 3: Polling RS-485 Display at Fixed Intervals

**What:** Reading the RS-485 display stream by polling UART at a fixed timer interval.

**Why bad:** The VS300FL4 uses a synchronous clock+data protocol. Pin 6 is the clock signal and Pin 5 carries data, both running at 60Hz. Polling at a fixed interval will miss frames, read partial data, and produce garbage. This is not an async UART stream you can read whenever -- it is a clocked synchronous signal.

**Instead:** Use interrupt-driven reading triggered by Pin 6 clock edges, or use ESPHome's UART component with careful frame synchronization. The MagnusPer project handles this by synchronizing reads to the clock signal.

### Anti-Pattern 4: Stateful Setpoint Tracking Without Verification

**What:** Tracking the setpoint by incrementing/decrementing a counter on each button press without any re-home or verification mechanism.

**Why bad:** Every missed press, manual panel adjustment, or power cycle silently desynchronizes the counter. Over days or weeks, drift accumulates. The automation sends 5 presses thinking it's going from 99F to 104F, but the tub is actually at 97F (missed 2 presses earlier) and ends up at 102F.

**Instead:** Re-home on every setpoint change (Phase 1), or verify via display reading (Phase 2).

### Anti-Pattern 5: Monolithic Firmware

**What:** Putting all logic (button injection, display decoding, climate entity, automation) into a single ESPHome YAML file with inline lambdas.

**Why bad:** The button injection timing, display protocol decoding, and climate state machine are each complex enough to warrant separate components. Inline lambdas become unmaintainable and untestable beyond ~20 lines.

**Instead:** Use the external component pattern with separate C++ files. The climate entity, GPIO output abstraction, and RS-485 decoder should be distinct classes with clear interfaces.

## Scalability Considerations

This is a single-installation project. Scalability is not a primary concern, but the architecture should support:

| Concern | Phase 1 | Phase 2 | Community Release |
|---------|---------|---------|-------------------|
| Configuration | Hardcoded GPIO pins, timing constants in C++ | Add YAML-configurable parameters | Fully parameterized YAML config |
| Portability | Works only with VS300FL4 + VL-panel | Same | Documented for other VS-series boards |
| Power source | USB battery (tethered) | USB battery | Board-powered via B0505S-1W DC-DC |
| Reliability | Re-home on every change (brute force) | Display verification, skip re-home when confirmed | Graceful degradation if display read fails |
| Testing | Manual verification at tub | Python test scripts for protocol decoding | Automated tests for protocol parser |

## Component Build Order

Dependencies dictate the build sequence. Each component builds on the one before it.

```
Phase 1: Open-Loop Button Injection
  1. GPIO output config (photorelay drivers)          -- no dependencies
  2. Button press timing (pulse + delay)              -- depends on 1
  3. Climate entity skeleton (target_temp only)        -- depends on 2
  4. Re-home algorithm                                 -- depends on 2, 3
  5. HA TOU automation                                 -- depends on 3

Phase 2: Closed-Loop Display Reading
  6. Temperature ladder capture (at tub)               -- depends on working Phase 1
  7. 7-segment lookup table (from ladder data)         -- depends on 6
  8. RS-485 frame decoder (UART + clock sync)          -- depends on 7
  9. Wire current_temperature into climate entity      -- depends on 3, 8
  10. Verification logic (confirm setpoint applied)    -- depends on 9

Phase 3: Community Release
  11. Parameterize all config (YAML-driven)            -- depends on 1-10
  12. Documentation (protocol, wiring, setup)          -- depends on all
  13. Publish ESPHome external component               -- depends on 11, 12
```

**Critical path:** Steps 1-5 can proceed now (parts in transit, firmware can be written ahead). Steps 6-7 are blocked on physical access to tub + RS-485 adapter. Step 8 is blocked on step 7 (need the lookup table to validate decoding).

**Parallelizable:** Steps 1-4 (firmware) and step 5 (HA automation YAML) are independent and can be developed simultaneously. The temperature ladder capture (step 6) can happen in parallel with firmware testing once parts arrive.

## Key Architectural Decisions

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| ESPHome external component (C++) over pure YAML | Button sequencing, re-home algorithm, and display decoding are too complex for YAML lambdas. C++ gives proper state machines, timing control, and testability. | Pure YAML with lambdas (rejected: unmaintainable), Arduino firmware (rejected: lose ESPHome/HA integration) |
| Climate entity over switches/buttons | HA climate entity natively supports target_temperature + current_temperature, which maps perfectly to setpoint control + display reading. TOU automations use standard `climate.set_temperature` service. | Individual button entities (rejected: HA automation would need to count presses itself), Number entity (rejected: no heating state tracking) |
| Separate write and read paths | Button injection (write) is proven and simple. Display decoding (read) is complex and unproven for VS-series. Keeping them independent means Phase 1 delivers value without blocking on Phase 2 research. | Monolithic component (rejected: couples proven and unproven work), Read-first approach (rejected: reading doesn't help without write path) |
| Re-home over relative adjustment | Eliminates all drift sources at the cost of ~50 extra button presses per setpoint change (~25 seconds). For TOU automation that changes setpoint 2-4 times per day, this is acceptable. | Relative adjustment with drift correction (rejected: requires display reading which is Phase 2), Trust the counter (rejected: fragile) |

## Reference Projects

| Project | Relevance | What to Learn |
|---------|-----------|---------------|
| [MagnusPer/Balboa-GS510SZ](https://github.com/MagnusPer/Balboa-GS510SZ) | Closest protocol match -- synchronous clock+data for GS-series with VL panels | Clock synchronization, 7-segment decoding, OR-gate button injection pattern |
| [brianfeucht/esphome-balboa-spa](https://github.com/brianfeucht/esphome-balboa-spa) | Best ESPHome external component structure for spa control | Component organization, optional sub-components, CRC error handling, retry logic |
| [netmindz/balboa_GL_ML_spa_control](https://github.com/netmindz/balboa_GL_ML_spa_control) | GL/ML display protocol (predecessor to VS-series) | Display multiplexing, segment mapping, MQTT bridge pattern |
| [Ylianst/ESP-IQ2020](https://github.com/Ylianst/ESP-IQ2020) | High-quality ESPHome external component for different spa brand | Component structure, configuration patterns, documentation approach |
| [jrowny/ESPHomeSpa](https://github.com/jrowny/ESPHomeSpa) | Simple ESPHome spa control | Minimal viable approach |

## Sources

- MagnusPer/Balboa-GS510SZ: https://github.com/MagnusPer/Balboa-GS510SZ (HIGH confidence -- closest architectural reference)
- brianfeucht/esphome-balboa-spa: https://github.com/brianfeucht/esphome-balboa-spa (HIGH confidence -- proven ESPHome external component pattern)
- ESPHome Climate Component: https://esphome.io/components/climate/ (HIGH confidence -- official docs)
- ESPHome External Components: https://esphome.io/components/external_components/ (HIGH confidence -- official docs)
- ESPHome GPIO Switch: https://esphome.io/components/switch/gpio/ (HIGH confidence -- official docs)
- ESPHome UART Bus: https://esphome.io/components/uart/ (HIGH confidence -- official docs)
- ESPHome GPIO Output: https://esphome.io/components/output/gpio/ (HIGH confidence -- official docs)
- Home Assistant Climate Entity: https://developers.home-assistant.io/docs/core/entity/climate/ (HIGH confidence -- official docs)
- HA Community Balboa Thread: https://community.home-assistant.io/t/balboa-hot-tub-spa-automation-and-power-savings/353032 (MEDIUM confidence -- community experience)
- netmindz/balboa_GL_ML_spa_control: https://github.com/netmindz/balboa_GL_ML_spa_control (MEDIUM confidence -- different protocol generation but similar approach)

---

*Architecture research: 2026-03-13*
