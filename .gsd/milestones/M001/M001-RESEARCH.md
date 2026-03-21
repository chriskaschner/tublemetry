# Project Research Summary

**Project:** Tubtron -- ESP32 Hot Tub Automation (Balboa VS300FL4)
**Domain:** ESP32 embedded firmware + Home Assistant integration for TOU energy optimization
**Researched:** 2026-03-13
**Confidence:** HIGH (stack, architecture, Phase 1 pitfalls well-validated; Phase 2 protocol decoding is the primary uncertainty)

## Executive Summary

Tubtron is a bridge device: an ESP32 running ESPHome firmware sits between a Balboa VS300FL4 hot tub control board and Home Assistant, translating HA climate commands into analog button presses. The core value proposition is Time-of-Use rate optimization -- holding the tub at 99F during on-peak hours and raising it to 104F off-peak, saving roughly $10/month. The approach is non-invasive: the hot tub board is completely unmodified, and the ESP32 taps existing RJ45 panel pins via optoisolated photorelays to simulate button presses. This button injection strategy is proven (manual bridging test already confirmed it works), heavily precedented in the Balboa community (GS-series projects), and is the only viable command path for the VS-series because no digital command channel exists.

The recommended implementation is an ESPHome external component (C++) that exposes a HA climate entity from day one. This is a deliberate architectural choice: a proper climate entity gives HA a thermostat card and `climate.set_temperature` service from Phase 1, avoiding any migration later. All four built-in ESPHome climate platforms were rejected because they implement heating control logic -- the VS300FL4 already has its own thermostat, and two control loops fighting each other is both unnecessary and potentially dangerous. A minimal custom climate class (~100-200 lines C++) that accepts a target temperature, runs the re-home button sequence, and reports the setpoint back to HA is the correct abstraction. Phase 2 adds RS-485 display reading to upgrade from open-loop to closed-loop operation.

The principal risks are hardware-level: analog noise on button lines causing phantom presses (directly observed in testing), ESP32 boot-time GPIO glitches on strapping pins, and open-loop drift from missed or extra presses. All three are mitigated by design choices already in place -- AQY212EH photorelays for galvanic isolation, careful GPIO pin selection (GPIO 16/17/18/19 are safe), and a re-home strategy that slams to the 80F floor before counting up. Phase 2 (display reading) remains uncharted territory for the VS-series specifically, with no existing published automation for this board family -- budget extra time and treat it as active reverse engineering, not a known-pattern implementation.

## Key Findings

### Recommended Stack

ESPHome 2026.2.x on ESP32 WROOM-32 is the unambiguous choice for this project. ESPHome provides native Home Assistant integration (no MQTT broker required), OTA firmware updates, and a mature external component API -- all critical for a device that will live inside a tub enclosure. ESP-IDF (now the default framework in ESPHome 2026.1+) produces 40% smaller binaries and faster compile times vs. Arduino; there is no reason to override it. Home Assistant handles all TOU scheduling via standard time-trigger automations calling `climate.set_temperature`. The Python analysis tools already in the repo (pyserial, numpy) remain relevant for offline RS-485 protocol analysis in Phase 2.

**Core technologies:**
- ESPHome 2026.2.x: firmware framework and HA integration -- native API, OTA, climate entity, external components; the only serious option for ESP32+HA projects
- ESP-IDF (default): underlying ESP32 framework -- smaller binaries, faster compiles; do not override to Arduino unless a specific component requires it
- Custom external climate component (C++): hot tub interface -- only way to expose setpoint control as a proper HA climate entity without fighting the board's built-in thermostat
- AQY212EH photorelays + 680R resistors: button injection circuit -- galvanic isolation between ESP32 3.3V and tub 5V analog domain; non-negotiable for noise immunity
- Home Assistant 2026.3.x automations: TOU scheduling -- standard `climate.set_temperature` on time triggers, no extra platform needed
- MAX485 transceiver (Phase 2): RS-485 display reading -- level shifting for synchronous clock+data bus; power from tub +5V, not ESP32 3.3V

### Expected Features

**Must have (table stakes -- Phase 1):**
- Set target temperature via HA climate entity -- core TOU automation path
- Temp Up / Temp Down button simulation -- proven by manual bridging test, only viable command path
- Re-home sequence (25x down to 80F floor, then count up) -- required for open-loop accuracy without display feedback
- TOU schedule automation in HA -- two automations, weekday 10am and evening triggers
- Firmware-level temperature bounds (80-104F clamp) -- safety requirement, hardware max is CPSC-mandated 104F
- OTA firmware updates -- non-negotiable; ESP32 will be physically inaccessible once installed
- WiFi with auto-reconnect and fallback AP -- must self-heal; missed TOU transition costs money

**Should have (differentiators -- Phase 2):**
- RS-485 display reading (current temperature) -- upgrades to closed-loop; detects drift, manual overrides, board errors
- Drift detection and auto-correction -- depends on closed-loop; eliminates accumulated error from missed presses
- Freeze protection awareness -- parse display for ICE/OH codes; suppress automation during protection events

**Defer (Phase 1.5 and later):**
- Lights/Jets control -- same circuit pattern, low effort, but not required for TOU; add after MVP proven
- Board-powered operation (B0505S-1W DC-DC) -- USB battery is fine for prototyping
- Energy cost tracking -- more meaningful with Phase 2 current temperature sensor
- Community publication -- Phase 3 milestone; requires documentation and repo cleanup

**Anti-features (explicitly excluded):**
- RS-485 command injection -- no digital command channel exists; analog injection is the proven, safe path
- PID control on ESP32 -- tub board has its own thermostat; second control loop would fight it
- Cloud connectivity, mobile app, geofencing, ML prediction -- all overkill for a fixed TOU schedule; HA already provides mobile access

### Architecture Approach

The system is a bridge pattern: ESP32 + ESPHome sits between HA and the VS300FL4, translating climate commands into analog button presses (write path) and, in Phase 2, RS-485 display data into temperature readings (read path). The hot tub board is completely unmodified and unaware of the ESP32. The write path and read path are independent subsystems within the external component, meaning Phase 1 delivers full functionality without any Phase 2 code in place. This separation is a deliberate design choice to avoid coupling proven work (button injection) with unproven work (protocol decoding).

**Major components:**
1. Home Assistant -- TOU automation scheduling and climate entity display; communicates with ESP32 via ESPHome native API over WiFi
2. ESPHome firmware (custom external climate component) -- climate entity, re-home algorithm, button press sequencing, setpoint state management; the core bridge logic
3. GPIO output layer + photorelays -- momentary pulse generation; galvanic isolation between ESP32 3.3V and tub 5V analog domain; prevents noise coupling and ground loops
4. RS-485 read layer (Phase 2) -- ISR-driven synchronous clock+data decoder; feeds `current_temperature` into existing climate entity without modifying the write path
5. VS300FL4 board + VL-series panel -- completely unmodified; board reads analog button lines, panel displays temperature

**Build order (dependency-driven):**
- GPIO output config -> button press timing -> climate entity skeleton -> re-home algorithm -> HA automation (Phase 1, sequential)
- Temperature ladder capture -> 7-segment lookup table -> RS-485 frame decoder -> `current_temperature` wired in -> verification logic (Phase 1.5 + Phase 2, sequential)
- Parameterize config -> documentation -> publish (Phase 3)

### Critical Pitfalls

1. **Phantom presses from analog noise on button lines** -- use AQY212EH photorelays (already designed in), keep wiring <6 inches, add 100nF caps on button lines; this was directly observed during this project's initial testing with an unterminated breakout cable
2. **Boot-time GPIO glitches on strapping pins** -- assign photorelay outputs to GPIO 16, 17, 18, 19 only (never GPIO 0, 2, 5, 12, 15); verify with logic analyzer before connecting photorelays; consider hardware enable gate
3. **Open-loop drift from missed or extra presses** -- empirically characterize timing in Task 3 (this is a gate, not optional); use 2x safety margins on all timing parameters; always run full re-home, never incremental adjustments
4. **Interfering with Balboa safety systems** -- firmware clamp to 80-104F range is mandatory; add outdoor temperature weather gate in HA automation (skip transitions when ambient < 35F); parse OH/ICE display codes in Phase 2
5. **WiFi disconnects causing missed TOU transitions** -- set `power_save_mode: none`, use static IP, implement `on_disconnect` fallback behavior; measure signal strength at tub location before deploying permanently

## Implications for Roadmap

The phase structure is already well-defined by hardware dependencies and the open-loop vs. closed-loop distinction. Three phases, with one intermediate capture step, are the right decomposition.

### Phase 1: Button Injection MVP (Open-Loop)

**Rationale:** The write path is fully proven (manual bridging test), hardware is arriving, and display reading is not required for TOU automation to function. This phase delivers the core value proposition. Firmware can be written and compiled ahead of parts arrival.

**Delivers:** Working ESPHome firmware with custom climate entity, functional re-home sequence, HA TOU automations running on schedule, empirically validated button timing parameters.

**Addresses:** Set target temperature, button simulation, re-home, TOU automation, OTA, WiFi, safety bounds (all table stakes features).

**Avoids:** Boot-time GPIO glitches (safe pin selection, Task 1), analog noise (photorelay circuit, Task 2), timing drift (empirical characterization, Task 3), safety system interference (weather gate, Task 4), race conditions in re-home sequence (script mode: single, global flag).

### Phase 1.5: Temperature Ladder Capture (Phase 2 Prerequisite)

**Rationale:** Phase 2 is hard-blocked on this. The 72 unresolved 7-segment byte mappings cannot be decoded without a controlled capture at known temperatures. This is a physical hardware task that must precede any Phase 2 firmware development.

**Delivers:** Complete 7-segment lookup table, committed capture files with descriptive names, CAPTURES_INDEX.md.

**Addresses:** Prerequisite for current temperature display, drift detection, freeze protection awareness.

**Avoids:** The data overwrite pitfall -- use CAPTURES_INDEX.md, date-stamped filenames, immediate git commit after each capture.

### Phase 2: Closed-Loop Display Reading

**Rationale:** RS-485 display reading upgrades from open-loop (trust the press counter) to closed-loop (verify against actual display). This eliminates drift errors and enables drift detection, manual override recovery, and freeze protection parsing. It is the hardest phase -- the VS300FL4 synchronous clock+data protocol has no published documentation. Treat it as active reverse engineering.

**Delivers:** `current_temperature` populated in the HA climate entity, drift detection logic, error code parsing (OH/ICE), full thermostat card with current + target temperature.

**Addresses:** Display stream decoding, current temperature, drift detection/correction, freeze protection awareness.

**Avoids:** Polling anti-pattern (must use ISR-driven clock-edge reading, not timer polling), MAX485 voltage mismatch (level shifter or voltage divider on RO pin), monolithic firmware (extend existing external component, do not rewrite).

### Phase 3: Community Release

**Rationale:** Publishing the first working VS-series automation is an explicit project goal. This phase polishes the implementation for public consumption with fully parameterized YAML config, protocol documentation with supporting capture files, and wiring diagrams.

**Delivers:** Published ESPHome external component, protocol documentation with empirical evidence, wiring guide, setup instructions.

**Addresses:** First published VS-series automation milestone.

**Avoids:** Publishing unverified protocol documentation -- all claims must be backed by capture data.

### Phase Ordering Rationale

- Phase 1 before Phase 2: Write path is independent of read path. TOU value can be delivered immediately without waiting for protocol reverse engineering.
- Phase 1.5 before Phase 2: Display decoding is gated on the lookup table, which is gated on physical ladder capture. Hardware dependency, not resolvable in software.
- Phase 2 before Phase 3: Community publication requires a complete, verified, reliable implementation.
- Re-home on every setpoint change throughout Phase 1: Bounds worst-case drift to one sequence and prevents accumulation. The 15-30 second cost per TOU transition is acceptable.

### Research Flags

Phases needing deeper research during planning:
- **Phase 2:** VS-series RS-485 protocol is partially characterized but not fully specified. Frame sync pattern, state machine, and status flag byte positions need empirical resolution during and after the ladder capture. The MagnusPer/GS510SZ source is a reference, not a specification -- the VS300FL4 frame structure may differ.

Phases with standard patterns (skip additional research):
- **Phase 1:** ESPHome external component pattern is well-documented (ESP-IQ2020, esphome-balboa-spa as direct references), button injection circuit is validated, re-home strategy is designed. Stack is fully specified.
- **Phase 1.5:** Capture methodology is established (Python scripts exist). Operational task, not exploratory.
- **Phase 3:** OSS publication is standard practice. No domain-specific research gaps.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All technology choices verified against official ESPHome docs and working reference projects. ESP-IDF default, external component pattern, climate entity abstraction all confirmed. |
| Features | HIGH | Feature set tightly scoped to TOU optimization. Table stakes validated by existing proof-of-concept. Anti-features clearly justified. |
| Architecture | HIGH | Bridge pattern well-precedented in Balboa community (GS510SZ, esphome-balboa-spa). Component boundaries and data flow are clean. Build order is dependency-correct. |
| Pitfalls (Phase 1) | HIGH | Most Phase 1 pitfalls are directly observed or extensively documented. GPIO strapping behavior, WiFi instability, and analog noise are all confirmed community knowledge. |
| Pitfalls (Phase 2) | MEDIUM | Protocol reverse engineering has inherent uncertainty. The VS-series frame structure differences from GS-series are unknown until empirically characterized. |

**Overall confidence:** HIGH for Phase 1. MEDIUM for Phase 2 (protocol reverse engineering has irreducible uncertainty until ladder capture is complete).

### Gaps to Address

- **Button timing parameters:** Minimum press duration, inter-press gap, and auto-repeat threshold for the VS300FL4 are undocumented. Must be empirically measured during Phase 1 Task 3. Starting values (500ms press, 400ms gap) are conservative estimates, not validated.
- **Photorelay on-resistance adequacy:** AQY212EH's 25 ohm on-resistance may or may not be sufficient to trigger the board's button detection threshold. The internal pull-down impedance is unknown. Resolve with multimeter during Phase 1 Task 2 breadboard testing.
- **VS300FL4 display frame structure:** Full frame sync pattern, state machine, and byte positions are not yet characterized. The 72 unresolved 7-segment mappings are the primary Phase 2 unknown. The temperature ladder capture is the only resolution path.
- **WiFi signal strength at installation site:** ESP32 reliability at the physical tub location is unknown. Must be measured before committing to a permanent installation. May require a range extender or dedicated access point.
- **Board rate-limiting / auto-repeat behavior:** Whether holding a button triggers auto-repeat (and at what duration) is unknown. This affects whether the re-home sequence can be optimized by holding rather than pulsing.

## Sources

### Primary (HIGH confidence)
- ESPHome official docs (esphome.io): ESP32 platform, climate component, external components, GPIO output, OTA, security best practices
- Home Assistant developer docs (developers.home-assistant.io): climate entity specification
- ESP-IDF official docs (Espressif): GPIO interrupts, strapping pin behavior
- ESPHome 2026.1.0 changelog: ESP-IDF default transition
- ESPHome 2026.2.0 changelog: compile improvements

### Secondary (MEDIUM confidence)
- MagnusPer/Balboa-GS510SZ (GitHub): closest architectural reference for synchronous clock+data protocol; GS-series, not VS-series -- treat as reference, not specification
- brianfeucht/esphome-balboa-spa (GitHub): best ESPHome external component structure for spa control
- Ylianst/ESP-IQ2020 (GitHub): high-quality ESPHome external component pattern for different spa brand
- ESPHome GitHub issues (#3094, #1237, #1196, #3885, #5025): GPIO boot behavior, WiFi stability, race conditions
- HA Community Balboa automation thread: community experience with Balboa automation

### Tertiary (supporting / contextual)
- Random Nerd Tutorials ESP32 pinout reference: GPIO safety classification
- espboards.dev strapping pins guide: boot-time GPIO behavior
- Leslie's Pool error code docs: OH/OHH/ICE definitions
- SpaGuts freeze protection docs: 45F trigger threshold documentation
- Project captures and analysis: 485/rs485-status-2026-03-08.md, 485/scripts/decode_7seg.py

---
*Research completed: 2026-03-13*
*Ready for roadmap: yes*

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

# Feature Landscape

**Domain:** ESP32-based hot tub automation via button injection + Home Assistant
**Researched:** 2026-03-13

## Table Stakes

Features that must exist for the system to deliver its core value (TOU rate optimization).

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Set target temperature via HA | Core value -- TOU automation requires programmatic temp control | Medium | Phase 1. Custom climate entity (external component) with target_temperature. HA gets a thermostat card from day one. |
| Temp Up / Temp Down button simulation | Only viable command path to VS300FL4 | Low | GPIO -> 680R -> AQY212EH -> button pin. Proven by manual bridging test. |
| Re-home sequence (slam to floor + count up) | Open-loop control requires known starting point to avoid cumulative drift | Medium | 25x Temp Down to guaranteed 80F floor, then N presses up. Eliminates drift from missed presses, manual overrides, power cycles. |
| TOU schedule automation | The entire reason this project exists (~$10/month savings) | Low | Two HA automations: weekday 10am -> 99F, evening -> 104F. Standard `climate.set_temperature` service call. |
| Safe temperature bounds | 4kW heater, humans sit in the water. CPSC max 104F. | Low | Firmware-level clamp: min 80F, max 104F. Board has hardware high-limit switch as backstop, but firmware must not rely on it. |
| OTA firmware updates | ESP32 will be inside/near tub enclosure, inaccessible for USB | Low | ESPHome built-in. Critical for iteration without physical access. |
| WiFi with auto-reconnect | Must maintain reliable connection to HA. Drops must self-heal. | Low | ESPHome `wifi:` handles reconnection. Add `ap:` fallback for recovery. |
| Fallback AP mode | Recovery path if WiFi credentials change or router dies | Low | ESPHome built-in. Prevents bricking. |
| Logging and observability | Must know what the system commanded, when, and whether it succeeded | Low | ESPHome `logger:` + HA state history. |

## Differentiators

Features that move beyond MVP. Not strictly required for TOU but significantly improve reliability or UX.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Display stream decoding (current temp) | Closed-loop verification. Detect missed presses, manual overrides, board resets. | High | Phase 2. Add ISR-driven synchronous protocol decoder to existing external component. Hardest part of the project. |
| Current temperature in climate entity | Proper thermostat card with current + target temp. Phase 1 shows target only. | Medium | Phase 2. Wire decoded display temp into climate entity's `current_temperature`. |
| Button timing characterization | Optimize press duration and inter-press gap for max reliability | Medium | Phase 1 empirical testing at the tub. Min press duration, auto-repeat threshold, inter-press gap. |
| Drift detection and auto-correction | Compare display reading vs expected state, auto re-home on mismatch | Medium | Phase 2. Depends on closed-loop display reading. |
| Lights/Jets control via HA | Convenience automation (lights before soak, jets on schedule) | Low | Extra photorelays on Pin 3/Pin 7. Same circuit pattern. |
| Board-powered operation | Eliminate USB battery, run permanently from board +5V via isolated DC-DC | Low | B0505S-1W already ordered. Hardware change only, firmware unchanged. |
| Energy cost tracking | Quantify actual savings from TOU optimization | Low | HA utility_meter + template sensors. More meaningful with Phase 2 temp sensor. |
| Freeze protection awareness | Detect and accommodate board's freeze protection mode | Medium | Phase 2. Pause TOU scheduling during freeze events. |
| First published VS-series automation | No one has published working automation for any VS300/VS500Z board | Medium | Community contribution milestone. Requires documentation quality and repo cleanliness. |

## Anti-Features

Features to explicitly NOT build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| RS-485 command injection | VS-series has no documented digital command channel. Panel is dumb analog. Could corrupt display stream or confuse board. | Stick to analog button injection. This is the proven, safe path. |
| Mobile app or standalone UI | HA already provides mobile app, dashboards, voice control. Massive duplication for zero benefit on a single-installation project. | Use HA's built-in mobile app and dashboard. |
| PID temperature control on ESP32 | Hot tub board already has its own thermostat. Second PID layer creates oscillation. | Set the target temperature. Let the VS300FL4 control the heater. |
| Cloud connectivity | Adds attack surface, latency, internet dependency. ESPHome native API is local-only and faster. | Use ESPHome native API. No MQTT, no cloud. |
| Replacing the VS300FL4 board | BP-series replacement costs $400-800. Defeats cost-saving purpose. | Work with the existing board. |
| Water quality monitoring | Requires separate probes ($50-200), calibration, probe replacement. Scope creep. | Separate project if ever desired. |
| ML/usage pattern prediction | For a known fixed TOU schedule, simple time-based automation is deterministic and debuggable. ML is over-engineering. | Explicit HA automations with time triggers. |
| Geofencing for heating | Hot tub takes 2-4 hours to heat. Geofencing triggers minutes before arrival. Timing mismatch is fundamental. | Use time-based scheduling aligned with usage patterns. |

## Feature Dependencies

```
WiFi -> API -> HA Discovery -> TOU Automation
GPIO Output -> Button Simulation -> Re-home Script
Custom Climate Component (target_temperature) -> climate.set_temperature -> TOU Automation
= Phase 1 MVP (open-loop)

RS-485 Display Reading -> Decoded Current Temperature
Climate Component + current_temperature = Phase 2 (closed-loop)
Closed-Loop + Drift Detection = Reliable Unattended Operation

Published Docs + Working Firmware + Circuit Design = Phase 3 Community Contribution
```

## MVP Recommendation (Phase 1)

Prioritize:
1. **Custom climate component (external)** -- Exposes target_temperature to HA as a proper climate entity
2. **Temp Up / Temp Down button simulation** -- proven path, core mechanism
3. **Re-home sequence** -- makes open-loop viable
4. **TOU schedule automation** -- delivers the core value proposition
5. **OTA + WiFi + logging** -- ESPHome defaults, near-zero effort

Defer:
- **Display reading / current_temperature** (Phase 2): High complexity, blocked on temperature ladder capture, not required for TOU to function
- **Lights/Jets** (Phase 1.5): Not needed for TOU. Add after MVP proven
- **Board power** (Phase 1.5): USB battery is fine for prototyping
- **Energy tracking** (Phase 2+): Requires current temp sensor for meaningful calculations

## Sources

- ESPHome Climate Component: https://esphome.io/components/climate/
- ESPHome External Components: https://esphome.io/components/external_components/
- ESPHome GPIO Output: https://esphome.io/components/output/gpio/
- ESPHome Output Button: https://esphome.io/components/button/output/
- ESPHome Script/Repeat actions: https://esphome.io/automations/actions/
- Ylianst/ESP-IQ2020 (feature reference): https://github.com/Ylianst/ESP-IQ2020
- MagnusPer/Balboa-GS510SZ: https://github.com/MagnusPer/Balboa-GS510SZ
- HA Climate integration: https://www.home-assistant.io/integrations/climate/
- CPSC hot tub temperature warnings: https://www.cpsc.gov/Newsroom/News-Releases/1980/CPSC-Warns-Of-Hot-Tub-Temperatures

# Domain Pitfalls

**Domain:** Hot tub automation via ESP32 button injection (Balboa VS300FL4)
**Researched:** 2026-03-13

---

## Critical Pitfalls

Mistakes that cause rewrites, hardware damage, or safety incidents.

### Pitfall 1: Phantom Button Presses from Noise Coupling on Analog Lines

**What goes wrong:** The Balboa VS300FL4 topside panel uses analog voltage sensing for buttons -- idle ~2.3V, pressed ~4.7V (bridged to +5V). These high-impedance analog lines are extremely sensitive to noise. Any capacitive coupling, ground bounce, or EMI from nearby wiring can push the line voltage above the detection threshold, causing unintended temperature changes, jet activations, or light toggles.

**Why it happens:** The VL-series panel has no microcontroller and no debounce logic. It is a purely passive device: resistor dividers set idle voltage, and button presses bridge to +5V. The control board reads these as analog thresholds. Even an unterminated Cat5 breakout cable caused phantom Temp Up presses during this project's initial testing -- documented in `485/rs485-status-2026-03-08.md`.

**Consequences:**
- Temperature silently drifts up or down without user knowledge
- Jets or heater activate when nobody is in the tub, increasing energy costs
- In worst case, temperature could climb to 104F maximum during an unintended period
- Destroys trust in the automation system, defeating the project's purpose

**Prevention:**
- Use photorelays (AQY212EH) for galvanic isolation between ESP32 and button lines. This is already the design choice -- do not compromise it. Never use bare MOSFETs or analog switches without isolation.
- Keep wiring between the RJ45 breakout and photorelays as short as physically possible (<6 inches).
- Route button injection wires away from the RS-485 data lines (pins 5/6) and away from the 240V heater/pump wiring.
- Verify with multimeter that photorelay off-leakage (spec: 1uA max) does not shift idle voltage enough to cross the detection threshold.
- Add 100nF ceramic capacitors across each button line to ground at the RJ45 breakout to suppress high-frequency noise.

**Detection:** Unexpected temperature changes when the ESP32 is powered off or idle. Monitor RS-485 display stream (Phase 2) for temperature values that differ from the last commanded setpoint.

**Phase:** Phase 1 (button injection MVP) -- must be validated during breadboard testing (Task 2/3).

**Confidence:** HIGH -- directly observed during this project's testing.

---

### Pitfall 2: ESP32 GPIO Strapping Pins Firing Photorelays During Boot/Reset

**What goes wrong:** During power-on, reset, or OTA update, certain ESP32 GPIO pins briefly change state (high/low pulses lasting milliseconds). If photorelay control lines are connected to strapping pins (GPIO 0, 2, 5, 12, 15) or other pins with boot-time behavior, the photorelays will actuate during every boot cycle, causing unintended button presses on the hot tub.

**Why it happens:** The ESP32 uses strapping pins to determine boot mode (flash vs. normal execution). During the ~100ms boot sequence, these pins are driven to specific states by internal pull-ups/pull-downs and the bootloader. GPIO 5 and 15 are pulled HIGH during boot. GPIO 12 has an internal pull-down. Pins connected to the flash (GPIO 6-11) are completely off-limits.

**Consequences:**
- Every ESP32 reboot, OTA update, or power cycle triggers 1-3 phantom button presses
- Temperature changes by 1-3 degrees each time the ESP32 reboots
- With ESPHome's watchdog and WiFi reconnect behavior, reboots happen more often than expected
- Cumulative drift makes open-loop control unreliable

**Prevention:**
- Use only safe GPIO pins for photorelay outputs: GPIO 13, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33 are safe for output
- Specifically avoid GPIO 0, 2, 5, 12, 15 (strapping), GPIO 6-11 (flash), GPIO 34-39 (input-only, no output driver)
- Verify chosen pins with a logic analyzer or oscilloscope during boot before connecting to photorelays
- Consider adding a hardware enable gate: use a "safe" GPIO to enable photorelay power only after boot completes (on_boot priority 600 in ESPHome)

**Detection:** Temperature changes that correlate with ESP32 reboot events in the ESPHome log. Attach LED to photorelay output during testing and observe during power cycle.

**Phase:** Phase 1 (firmware config, Task 1) -- pin selection must happen before breadboard build.

**Confidence:** HIGH -- well-documented ESP32 hardware behavior, multiple community reports.

**Sources:**
- [ESP32 Strapping Pins Complete Guide](https://www.espboards.dev/blog/esp32-strapping-pins/)
- [ESPHome GPIO switch toggles on boot issue #3094](https://github.com/esphome/issues/issues/3094)
- [Random Nerd Tutorials ESP32 Pinout Reference](https://randomnerdtutorials.com/esp32-pinout-reference-gpios/)

---

### Pitfall 3: Open-Loop Temperature Drift from Missed or Extra Button Presses

**What goes wrong:** The "re-home" strategy (slam 25x to floor at 80F, then count up to target) assumes every simulated button press is registered by the control board. If even one press is missed (too short, noise rejected) or double-counted (press too long, auto-repeat triggered), the final setpoint is wrong by 1F or more per missed/extra press. Over multiple TOU transitions per day, errors accumulate.

**Why it happens:**
- Button press timing parameters are unknown. The minimum press duration, inter-press gap, and auto-repeat threshold for the VS300FL4 are not documented anywhere. They must be empirically measured.
- The photorelay has finite switching times (turn-on: ~0.5ms typical, turn-off: ~0.1ms for AQY212EH). If the firmware pulse duration is too close to the board's minimum detection threshold, some presses will be rejected.
- If the pulse is too long (e.g., >2 seconds), the board may interpret it as a "hold" and enter auto-repeat mode, adding extra increments.
- Manual panel interaction between automation cycles (user adjusts temp by hand) completely invalidates the assumed position.

**Consequences:**
- Target setpoint of 99F ends up at 97F or 101F
- Error compounds across 2 TOU transitions/day = potential 2-4F drift per day
- User discovers tub at wrong temperature, loses trust in automation
- No feedback mechanism to detect the error in Phase 1 (open-loop)

**Prevention:**
- Task 3 (timing characterization) is the critical gate: measure minimum press duration, maximum press rate, and auto-repeat threshold with empirical testing on the actual hardware
- Use conservative timing margins: if minimum press is measured at 100ms, use 200ms. If auto-repeat starts at 2s, cap press duration at 500ms.
- Always run the full re-home sequence (slam to floor + count up) rather than incremental adjustments. This bounds worst-case error to a single sequence rather than accumulating across multiple sequences.
- Add a "re-home interval" -- run the full re-home sequence before every setpoint change, not just on drift correction. The extra 15-30 seconds per transition is worth the reliability.
- Phase 2 (display reading) eliminates this class of error entirely by providing closed-loop feedback. Prioritize it.

**Detection:** In Phase 1, the only detection is manual verification (look at the tub display). In Phase 2, compare RS-485 display reading to commanded setpoint after each re-home sequence.

**Phase:** Phase 1 (Task 3 timing characterization), resolved fully in Phase 2 (closed-loop).

**Confidence:** HIGH -- inherent to open-loop control; the project design already acknowledges this.

---

### Pitfall 4: Interfering with Balboa Safety Systems (Freeze Protection, Overheat)

**What goes wrong:** The Balboa VS300FL4 has built-in safety systems: overheat protection (OH/OHH codes above 108-118F), freeze protection (activates all equipment when water drops below 45F), and high-limit switch (hardware thermal cutoff). Automation that fights these systems can create dangerous or expensive situations.

**Why it happens:**
- The automation lowers temperature to 99F during on-peak hours. If ambient temperature drops and freeze protection activates while the setpoint is low, the automation might fight it by sending "temp down" presses during a freeze event.
- The system cannot distinguish between "user changed the temp" and "board is in protection mode" without display reading.
- Rapid setpoint changes (25 presses down, then 24 presses up) during a protection event could confuse the board's state machine.

**Consequences:**
- Freeze protection disabled or interrupted: pipes freeze, pump and heater damaged, $2000+ repair
- Overheat protection circumvented: water exceeds safe temperature, burn hazard for humans
- High-limit switch trips repeatedly: nuisance, potential relay damage on control board
- The VS300FL4 is discontinued -- replacement boards are $400-800 (BP100G2 upgrade)

**Prevention:**
- Never automate during extreme weather without temperature verification (Phase 2)
- The setpoint range is 80F-104F. The board itself prevents going above 104F or below 80F, which provides a hardware safety floor. Do not attempt to bypass this.
- In Phase 1, add a "weather gate" to the HA automation: skip TOU transitions if outdoor temperature is below 35F (freeze risk) or above 100F (heater may be fighting ambient)
- The re-home sequence (slam to 80F) is safe because 80F is above the 45F freeze protection threshold and below the overheat threshold
- In Phase 2, read the display stream to detect OH/OHH/ICE error codes and suppress automation during error states

**Detection:** Look for the board displaying error codes (OH, OHH, ICE) or the high-limit tripping. In Phase 2, parse the display stream for these error patterns.

**Phase:** Phase 1 (HA automation, Task 4) must include weather gating. Phase 2 resolves with display reading.

**Confidence:** HIGH -- Balboa freeze protection documented at 45F trigger, overheat at 108-118F.

**Sources:**
- [Spa & Hot Tub Error Codes OH/OHH/OHS](https://lesliespool.com/blog/spa-hot-tub-error-codes-oh-ohh-omg.html)
- [Freeze Protection on Balboa Systems](https://www.spaguts.com/spagutsfaqs/support-freeze-protection-on-balboa-m7-systems)
- [Preventing Freeze Damage](https://lesliespool.com/blog/preventing-freeze-damage-to-a-spa-or-hot-tub.html)

---

### Pitfall 5: ESP32 WiFi Disconnects Causing Lost Automation Commands

**What goes wrong:** The ESP32 loses WiFi connectivity, Home Assistant cannot reach the device, and scheduled TOU transitions fail silently. The tub stays at whatever setpoint it was last commanded to, potentially running the 4kW heater at 104F through the entire on-peak rate period, costing the money the project was designed to save.

**Why it happens:** ESP32 WiFi stability is a known pain point in the ESPHome community. Common causes:
- Signal strength below -70dBm (hot tub is outdoors, potentially far from router)
- Router DHCP lease expiry causing reconnect storms
- Power save mode conflicts (ESP32 power save vs. connection keepalive)
- Mesh network handoff delays (10+ minutes in some cases)
- ESP32 watchdog resets triggered by WiFi stack hangs

**Consequences:**
- Missed TOU transitions -- tub heats at on-peak rates, $0.20/kWh instead of $0.05/kWh
- Stale setpoint persists for hours until WiFi recovers or human notices
- Multiple watchdog reboots can trigger phantom button presses (see Pitfall 2)
- Automation appears "working" in HA dashboard (last known state) while actually disconnected

**Prevention:**
- Measure WiFi signal strength at the tub location before deploying. Need better than -65dBm for reliability.
- In ESPHome config, set `power_save_mode: none` to prevent WiFi sleep
- Set static IP to avoid DHCP lease issues: `use_address`, `manual_ip` in ESPHome WiFi config
- Implement a fallback: if ESP32 loses HA connection for >30 minutes, execute a safe default (e.g., set temp to 99F as a compromise)
- Use the `on_disconnect` trigger in ESPHome's `api:` component to log disconnects and trigger fallback behavior
- Consider a WiFi range extender or dedicated access point near the tub

**Detection:** Monitor ESPHome device uptime and connection status in Home Assistant. Set up HA notification if device goes offline for more than 10 minutes.

**Phase:** Phase 1 (firmware config, Task 1; HA automation, Task 4). WiFi reliability testing during breadboard prototype.

**Confidence:** HIGH -- extensively documented in ESPHome community, multiple GitHub issues.

**Sources:**
- [ESPHome disconnects constantly issue #1237](https://github.com/esphome/issues/issues/1237)
- [ESP32 loses connection after 3h20m issue #1196](https://github.com/esphome/issues/issues/1196)
- [Dealing with ESPHome Disconnects](https://www.thefrankes.com/wp/?p=4693)
- [ESP32 Disconnects Randomly](https://www.espboards.dev/troubleshooting/issues/wifi/esp32-disconnects-randomly/)

---

## Moderate Pitfalls

### Pitfall 6: ESPHome Momentary Switch Race Conditions During Re-Home Sequence

**What goes wrong:** The re-home sequence fires 25 rapid button presses (slam to floor), then counts up to target. If each press is implemented as a `switch.turn_on` with `delay` + `switch.turn_off`, concurrent HA commands or ESPHome automations can interrupt the sequence mid-execution, leaving the setpoint at an unknown intermediate value.

**Why it happens:** ESPHome delays are asynchronous. While a delay is running, other code continues executing. If HA sends a new setpoint command while a re-home sequence is in progress, both sequences can interleave, producing unpredictable GPIO patterns. Additionally, ESPHome's `on_turn_on` automation can enter infinite loops if the switch receives multiple rapid triggers.

**Prevention:**
- Use a global boolean `is_rehoming` flag to gate all setpoint changes. Check it before starting any sequence.
- Implement the entire re-home sequence as a single ESPHome `script:` with `mode: single` (rejects new calls while running) or `mode: restart` (cancels in-progress and starts fresh).
- Never expose individual "Temp Up" / "Temp Down" buttons to HA -- only expose the target setpoint as a `climate` entity. The firmware should own the re-home logic entirely.
- Use `script.wait` before issuing the count-up sequence to ensure the slam-down is complete.

**Detection:** Setpoint ends up at unexpected values after automation triggers. ESPHome logs showing overlapping script executions.

**Phase:** Phase 1 (firmware config, Task 1).

**Confidence:** MEDIUM -- based on ESPHome automation architecture and documented race conditions in similar patterns.

**Sources:**
- [ESPHome race condition in modbus_controller issue #3885](https://github.com/esphome/issues/issues/3885)
- [Switch on_turn_on loop discussion](https://community.home-assistant.io/t/switch-on-turn-on-loop/761620)
- [ESPHome delay not properly working issue #5025](https://github.com/esphome/issues/issues/5025)

---

### Pitfall 7: Photorelay On-Resistance Not Low Enough to Trigger Button Detection

**What goes wrong:** The AQY212EH has 25 ohm on-resistance (per datasheet). The Balboa board's button detection circuit is a voltage divider: idle at ~2.3V, "pressed" means bridging to +5V. If the photorelay's 25 ohm series resistance drops enough voltage in the divider network that the button line doesn't reach the board's detection threshold, button presses won't register.

**Why it happens:** The board's internal pull-down resistor value on the button lines is unknown. If it is low (e.g., 1K ohm), the AQY212EH's 25 ohm is negligible (button sees ~4.95V). If the pull-down is higher impedance and the detection threshold is close to the idle voltage, the 25 ohm might matter. This is entirely dependent on the unknown internal circuit design.

**Prevention:**
- Measure with a multimeter during Task 2 (breadboard prototype): with photorelay actuated, measure voltage on the button line. Must be above the detection threshold (estimated >4.0V based on the manual test where bridging directly to +5V worked).
- The manual proof-of-concept (bridging Pin 1 to Pin 8 directly with wire) had ~0 ohm resistance. The photorelay adds 25 ohm. If the internal pull-down is >500 ohm, this is fine (voltage will be >4.7V).
- If 25 ohm is too much (unlikely but possible), the AQY210EH variant has 0.55 ohm on-resistance but lower voltage rating. Or use two AQY212EH outputs in parallel (12.5 ohm).

**Detection:** Button presses don't register during breadboard testing. Multimeter on button line shows voltage below expected threshold when photorelay is actuated.

**Phase:** Phase 1 (Task 2, breadboard prototype).

**Confidence:** LOW -- the 25 ohm is likely fine given the circuit topology, but cannot be confirmed without measurement. The existing CONCERNS.md already flags this.

---

### Pitfall 8: RS-485 Display Reading (Phase 2) is Harder Than Expected

**What goes wrong:** The VS-series uses a synchronous clock+data protocol that is completely undocumented. The closest reference (MagnusPer/Balboa-GS510SZ for GS-series) uses a similar but not identical protocol. Assumptions about frame structure, timing, or encoding that work for the GS510SZ may not transfer to the VS300FL4, requiring fresh reverse engineering.

**Why it happens:**
- 72 candidate 7-segment mappings remain unresolved (need physical temperature ladder capture)
- The display multiplexing (Pin 5 fires content, Pin 6 fires refresh at 60Hz with ~400us offset) is confirmed but the full state machine is not understood
- The Pin 5 data line carries both idle frames and button-response burst patterns, which need to be distinguished
- The GS510SZ protocol has 42 clock pulses per cycle (39 for display + 3 for buttons). The VS300FL4 may differ.
- No existing ESPHome custom component handles this protocol family

**Prevention:**
- The temperature ladder capture (Task 5) is non-negotiable. Do it before starting any Phase 2 code.
- Study the MagnusPer/Balboa-GS510SZ source code carefully, but treat it as a reference, not a specification. The VS300FL4 is a different board generation.
- Plan for writing a custom ESPHome component (C++) rather than trying to use existing UART or SPI components. The synchronous clock+data protocol does not match standard UART framing.
- Budget significant time: this is uncharted territory. No published automation exists for VS-series boards.

**Detection:** Decoded display values don't match the physical panel display. Timing misalignment causes corrupted readings. ESPHome custom component crashes or produces garbage data.

**Phase:** Phase 2 (display stream decoding). Phase 1.5 (temperature ladder capture) is the prerequisite.

**Confidence:** MEDIUM -- the protocol structure is partially understood from existing captures, but significant unknowns remain.

**Sources:**
- [MagnusPer/Balboa-GS510SZ](https://github.com/MagnusPer/Balboa-GS510SZ)
- [HA Community: Writing ESPHome custom component with proprietary synchronous serial protocol](https://community.home-assistant.io/t/expert-advice-sought-writing-an-esphome-custom-component-with-a-proprietary-synchronous-serial-protocol/735070)

---

### Pitfall 9: Manual Panel Interaction Invalidates Automation State

**What goes wrong:** A human presses Temp Up/Down on the physical panel while automation is running. The ESP32 has no knowledge of this change. Its internal model of the current setpoint is now wrong. The next re-home sequence will set the correct absolute temperature (because it re-homes to floor first), but until that happens, the ESP32's reported state in Home Assistant is stale.

**Why it happens:** The VL-series panel is purely analog. There is no digital feedback from button presses on the panel. The ESP32 cannot detect that someone pressed a button on the physical panel. In Phase 1, the ESP32 is completely blind to the actual setpoint.

**Prevention:**
- Accept this limitation in Phase 1. Document it clearly for users. The re-home strategy bounds the damage: the next scheduled transition will correct the setpoint.
- In Phase 2, display reading detects the actual current setpoint, eliminating this issue.
- Consider running a re-home sequence on a timer (e.g., every 2 hours) rather than only at TOU transition points, to correct for manual overrides faster.
- In the HA UI, display a caveat: "Reported temperature may be inaccurate if panel was used manually."

**Detection:** Only detectable in Phase 2 via display reading. In Phase 1, user must visually verify.

**Phase:** Acknowledged in Phase 1, resolved in Phase 2.

**Confidence:** HIGH -- inherent to the architecture.

---

### Pitfall 10: ESP32 Environmental Damage from Hot Tub Proximity

**What goes wrong:** The ESP32, breadboard, and wiring corrode, short, or fail due to humidity, chemical vapors (chlorine/bromine), water splashes, or temperature cycling. The hot tub environment combines high humidity, corrosive chemicals, and potential splash exposure -- the worst possible environment for bare electronics.

**Why it happens:** Breadboard contacts oxidize in humid environments. Chlorine vapor accelerates copper corrosion on PCB traces and jumper wire contacts. Temperature cycling (hot cover + cold outdoor air) causes condensation inside enclosures. Water splash from jets or cover removal can reach nearby electronics.

**Prevention:**
- Phase 1 (breadboard prototype) is explicitly temporary. Accept it will degrade. Plan to move to soldered protoboard or PCB within weeks, not months.
- Mount the ESP32 at least 3 feet from the tub edge and above the water line.
- Use an IP65-rated enclosure with cable glands for any permanent installation.
- Apply conformal coating to the final soldered board.
- Route the RJ45 cable (which goes to the tub) through a drip loop before entering the enclosure.
- Use silicone-sealed connectors, not bare screw terminals, for the final installation.

**Detection:** Intermittent WiFi disconnects, erratic GPIO behavior, visible corrosion on contacts, musty smell inside enclosure.

**Phase:** Phase 1 (breadboard is temporary), permanent enclosure should be planned for Phase 2/3 deployment.

**Confidence:** HIGH -- well-documented in outdoor ESP32 projects and hot tub electronics.

**Sources:**
- [How to Waterproof ESP32 for Outdoor IoT Applications](https://waterproofrd.com/how-to-waterproof-esp32-pk441/)
- [Hot tub control panel fogging/moisture damage](https://www.justanswer.com/pool-and-spa/tks7z-hot-tub-control-panel-fogging.html)

---

## Minor Pitfalls

### Pitfall 11: NVS Flash Wear from Frequent State Saves

**What goes wrong:** ESPHome's `restore_value: true` on globals writes to NVS flash on every state change. If the firmware logs temperature readings, counters, or timestamps to NVS on every sensor poll (e.g., every 60 seconds), it can wear the flash partition within months.

**Prevention:**
- Use `restore_value: true` only for the target setpoint and re-home state, not for rapidly changing values.
- Set ESPHome's `flash_write_interval` to at least 5 minutes (default is adequate for this use case).
- For Phase 2 display readings, store current temperature in RAM only, not NVS.

**Phase:** Phase 1 (firmware config, Task 1).

**Confidence:** MEDIUM -- ESP32 NVS wear leveling mitigates this significantly; mainly a concern if implementation is careless.

**Sources:**
- [Flash Memory Wear Effects of ESPHome Recovery](https://newscrewdriver.com/2022/03/25/flash-memory-wear-effects-of-esphome-recovery-esp8266-vs-esp32/)

---

### Pitfall 12: MAX485 Voltage Level Mismatch with ESP32

**What goes wrong:** The MAX485 modules (5x on hand for Phase 2 display reading) operate at 5V logic. The ESP32 GPIO pins are 3.3V. While ESP32 inputs are 5V-tolerant on some pins (undocumented, not officially supported), driving a 5V MAX485 from 3.3V ESP32 TX may produce marginal logic levels.

**Prevention:**
- For Phase 2 (read-only display tap), the MAX485 RX output goes to ESP32 input. Use a voltage divider (2K/3.3K) or a level shifter on the MAX485 RO pin.
- Power the MAX485 from the hot tub board's +5V (Pin 1), not from the ESP32's 3.3V.
- The B0505S-1W isolated DC-DC is already in the BOM for this exact purpose.
- The MAX485 DE/RE pins for read-only operation should be tied to GND (permanent receive mode), avoiding any GPIO control complexity.

**Phase:** Phase 2 (display reading).

**Confidence:** HIGH -- standard MAX485 + ESP32 integration concern, well-documented.

**Sources:**
- [MAX485 TTL to RS485 Interfacing with ESP32](https://hackatronic.com/max485-ttl-to-rs485-modbus-module-interfacing-with-esp32/)
- [ESP32 RS-485 Forum Discussion](https://esp32.com/viewtopic.php?t=36288)

---

### Pitfall 13: Home Assistant TOU Automation Edge Cases

**What goes wrong:** The HA automation for TOU scheduling (99F on-peak 10am-9pm weekdays, 104F off-peak) can fail on edge cases: holidays (rates may differ), DST transitions (spring forward creates a 23-hour day), HA restarts during a transition window, or concurrent automations racing to set different temperatures.

**Prevention:**
- Use HA's `time` trigger (not `time_pattern`) for precise scheduling
- Add a condition to check current setpoint before commanding a change (avoid redundant re-home sequences)
- Use `mode: single` on the automation to prevent concurrent execution
- For DST: test by temporarily shifting system clock
- For holidays: the $10/month savings is small enough that holiday exceptions are not worth the complexity. The worst case is heating at on-peak rate for one day (~$0.50 extra).
- Add a manual override input_boolean in HA to suppress automation (e.g., for parties, maintenance)

**Phase:** Phase 1 (Task 4, HA automation).

**Confidence:** MEDIUM -- standard HA automation concerns, not highly specific to this project.

---

### Pitfall 14: Overwriting Capture Data (Again)

**What goes wrong:** The project has already lost one critical capture file (`rs485_capture.txt` was overwritten with Pin 6 data, destroying the original Pin 5 button-press capture). As more captures are taken (especially the Phase 1.5 temperature ladder), files could be overwritten again without tracking what was lost.

**Prevention:**
- Create `485/CAPTURES_INDEX.md` before any new captures: filename, date, pin, test conditions, known temperature at capture time.
- Use descriptive filenames with dates: `rs485_pin5_templadder_104_to_99_2026-03-20.txt`
- Never reuse filenames. Append a suffix rather than overwriting.
- Commit captures to git immediately after taking them.

**Phase:** Phase 1.5 (temperature ladder capture, Task 5).

**Confidence:** HIGH -- already happened once in this project.

---

### Pitfall 15: Unsafe Temperature Command from Software Bug

**What goes wrong:** A firmware bug, HA automation error, or edge case causes the system to enter a loop that continuously presses Temp Up, or an integer overflow in the press counter produces an absurd number of presses.

**Why it happens:** Software bugs. A stuck GPIO, an off-by-one in the press counter, or an automation that fires twice could overshoot the target.

**Consequences:** The board itself clamps setpoint to 80-104F range, which is the hardware safety floor. The board also has a high-limit switch (110-120F hardware thermal cutoff). So the risk is bounded to 104F maximum setpoint, not runaway heating. But 104F during on-peak hours is the exact scenario the automation exists to prevent.

**Prevention:**
- Firmware-level hard clamp: reject any setpoint outside 80-104F range before generating button presses.
- Maximum press count limit: never send more than 24 presses in a single count-up cycle (104-80=24). Assert this in code.
- Watchdog timer: if the re-home script takes longer than expected (e.g., >2 minutes), abort.
- HA automation validation: use `input_number` with min/max constraints for setpoint targets.

**Detection:** HA logs showing commanded setpoints. Firmware logs showing press counts exceeding expected range.

**Phase:** Phase 1 (firmware config, Task 1; HA automation, Task 4).

**Confidence:** HIGH -- standard software safety concern; mitigated by the board's own 104F clamp.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Phase 1, Task 1: ESPHome firmware config | Wrong GPIO pin selection causes boot-time phantom presses (Pitfall 2) | Use only safe pins: GPIO 16, 17, 18, 19, 21, 22, 23, 25, 26, 27 |
| Phase 1, Task 1: ESPHome firmware config | Re-home sequence race conditions (Pitfall 6) | Use `script:` with `mode: single`; global `is_rehoming` flag |
| Phase 1, Task 2: Breadboard prototype | Photorelay on-resistance too high (Pitfall 7); loose breadboard contacts | Measure voltages empirically; use short, solid-core jumper wires |
| Phase 1, Task 3: Button timing characterization | Unknown timing causes missed/extra presses (Pitfall 3) | Measure with logic analyzer; use 2x safety margin on all timing params |
| Phase 1, Task 4: HA TOU automation | WiFi disconnect causes missed transition (Pitfall 5); edge cases (Pitfall 13) | Static IP, power_save_mode: none, fallback behavior on disconnect |
| Phase 1, Task 4: HA TOU automation | Fighting freeze protection (Pitfall 4) | Add outdoor temp weather gate; skip low-setpoint commands when ambient < 35F |
| Phase 1.5, Task 5: Temperature ladder capture | Data overwrite (Pitfall 14) | Descriptive filenames, capture index, immediate git commit |
| Phase 2: Display stream decoding | Protocol harder than expected (Pitfall 8); voltage mismatch (Pitfall 12) | Temperature ladder first; level shifter; budget extra time |
| Phase 2: Closed-loop control | Display reading errors cause wrong corrections | Validate decoded temp against expected range; require N consecutive matching reads before acting |
| Phase 3: Community publication | Publishing incorrect protocol documentation | Verify all claims against empirical data; include capture files as evidence |
| Long-term: Outdoor deployment | Environmental damage (Pitfall 10) | IP65 enclosure, conformal coating, drip loops |

---

## Sources

- [ESP32 Strapping Pins Complete Guide - espboards.dev](https://www.espboards.dev/blog/esp32-strapping-pins/)
- [ESP32 Pinout Reference - Random Nerd Tutorials](https://randomnerdtutorials.com/esp32-pinout-reference-gpios/)
- [How to Choose Safe GPIO Pins on ESP32 WROOM-32](https://www.samgalope.dev/2024/12/28/safe-and-unsafe-pins-to-use-in-an-esp32-wroom-32/)
- [ESPHome GPIO switch toggles on boot - GitHub issue #3094](https://github.com/esphome/issues/issues/3094)
- [ESPHome disconnects constantly - GitHub issue #1237](https://github.com/esphome/issues/issues/1237)
- [ESP32 loses connection after 3h20m - GitHub issue #1196](https://github.com/esphome/issues/issues/1196)
- [Dealing with ESPHome Disconnects - theFrankes.com](https://www.thefrankes.com/wp/?p=4693)
- [ESP32 Disconnects Randomly - espboards.dev](https://www.espboards.dev/troubleshooting/issues/wifi/esp32-disconnects-randomly/)
- [Spa & Hot Tub Error Codes OH/OHH/OHS - Leslie's](https://lesliespool.com/blog/spa-hot-tub-error-codes-oh-ohh-omg.html)
- [Freeze Protection on Balboa Systems - SpaGuts](https://www.spaguts.com/spagutsfaqs/support-freeze-protection-on-balboa-m7-systems)
- [Preventing Freeze Damage - Leslie's](https://lesliespool.com/blog/preventing-freeze-damage-to-a-spa-or-hot-tub.html)
- [MagnusPer/Balboa-GS510SZ - GitHub](https://github.com/MagnusPer/Balboa-GS510SZ)
- [ESPHome Custom Component for Synchronous Protocol - HA Community](https://community.home-assistant.io/t/expert-advice-sought-writing-an-esphome-custom-component-with-a-proprietary-synchronous-serial-protocol/735070)
- [Balboa Hot Tub Automation - HA Community](https://community.home-assistant.io/t/balboa-hot-tub-spa-automation-and-power-savings/353032)
- [Flash Memory Wear Effects of ESPHome - New Screwdriver](https://newscrewdriver.com/2022/03/25/flash-memory-wear-effects-of-esphome-recovery-esp8266-vs-esp32/)
- [MAX485 Interfacing with ESP32 - Hackatronic](https://hackatronic.com/max485-ttl-to-rs485-modbus-module-interfacing-with-esp32/)
- [How to Waterproof ESP32 for Outdoor IoT - Waterproofrd](https://waterproofrd.com/how-to-waterproof-esp32-pk441/)
- [ESP32 Noise Triggers Input Button Events - ESP32 Forum](https://esp32.com/viewtopic.php?t=23160)
- [ESPHome race condition in modbus_controller - GitHub issue #3885](https://github.com/esphome/issues/issues/3885)
- [ESPHome delay not properly working - GitHub issue #5025](https://github.com/esphome/issues/issues/5025)
- Project context: .planning/PROJECT.md, .planning/phases/01-button-injection-mvp/.continue-here.md, .planning/codebase/CONCERNS.md

---

*Pitfalls research: 2026-03-13*