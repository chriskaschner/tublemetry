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
