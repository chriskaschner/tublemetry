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
