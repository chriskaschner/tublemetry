# Tubtron

## What This Is

A hot tub automation system that controls a Balboa VS300FL4 controller via ESP32 and Home Assistant. It simulates physical button presses through photorelays to adjust temperature setpoints on a Time-of-Use electricity schedule, saving ~$10/month on MGE Rg-2A rates without manual intervention.

## Core Value

The tub automatically lowers its setpoint during on-peak hours and raises it before evening use -- no human involvement required.

## Requirements

### Validated

- Confirmed RJ45 pinout: +5V (pin 1), GND (pin 4), analog button lines (pins 2/3/7/8), RS-485 data (pins 5/6)
- Confirmed button simulation works: bridging +5V to button pin changes setpoint
- Confirmed synchronous clock+data protocol (NOT RS-485 UART): Pin 6=clock, Pin 5=data, 24 bits/frame at 60Hz
- Full 7-segment lookup table confirmed via ladder capture (2026-03-20): all digits 0-9, mode letters E/c/L/t/H
- VS300FL4 uses 0x73 for "9" (no bottom segment), differs from GS510SZ reference (0x7B)

### Active

- [ ] ESP32 + photorelay circuit simulates Temp Up/Down button presses
- [ ] ESPHome firmware exposes climate entity to Home Assistant
- [ ] "Re-home" strategy: slam 25x to floor (80F), count up to target
- [ ] Home Assistant TOU automation: 99F on-peak (10am-9pm weekdays), 104F off-peak
- [ ] Display stream decoding for closed-loop temperature verification (ESPHome firmware needs GPIO rewrite)
- [x] Temperature ladder capture to resolve 7-segment encoding ambiguity (completed 2026-03-20)
- [ ] Published protocol documentation and ESPHome component for community

### Out of Scope

- Replacing the VS300FL4 board with a BP-series controller -- too expensive (~$500+), defeats the purpose
- Sending digital RS-485 commands to the board -- VS-series has no documented command channel; panel is dumb analog
- Mobile app or standalone UI -- Home Assistant handles all user interaction
- Multi-tub support -- single installation, single controller

## Context

- Hot tub: Strong Spas Rockport S6-0001 (Costco "Evolution"), rotomolded, ~300 gal, 4kW heater, 2BHP pump, 240V
- Controller: Balboa VS300FL4 (PCB is VS500Z, P/N 22972_E2), discontinued VS-series generation
- Topside panel: VL-series (VL401/VL403/VL406U), no microcontroller, purely analog buttons and 7-segment display
- VS-series uses synchronous clock+data protocol, not the standard BWA 0x7E-framed protocol -- no published automation exists
- MagnusPer/Balboa-GS510SZ is the closest reference (similar synchronous architecture for GL/ML boards)
- All reverse-engineering done on Windows with USB RS-485 adapter and 8-channel logic analyzer
- BOM ordered from AliExpress (~$6 total), 2-4 week lead time

## Constraints

- **Hardware**: Must use existing VS300FL4 board -- no board replacement
- **Interface**: Analog button injection only viable command path (panel has no MCU)
- **Isolation**: Photorelays (AQY212EH) required for galvanic isolation on sensitive analog lines
- **Power**: ESP32 USB-powered initially; B0505S-1W isolated DC-DC for future board-powered operation
- **Platform**: Target platform is ESPHome on ESP32 WROOM-32, integrated with Home Assistant
- **Parts**: AliExpress order in transit (ESP32, photorelays, RJ45 breakouts, resistors, DC-DC converter)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Photorelay over MOSFET | Galvanic isolation prevents noise coupling on sensitive analog button lines; phantom presses observed with unterminated cable | -- Pending |
| Re-home strategy (slam to floor + count up) | Eliminates drift/sync issues; 25 presses guarantees 80F floor regardless of starting point | -- Pending |
| ESPHome over custom firmware | Native Home Assistant integration, OTA updates, YAML config, large community | -- Pending |
| Open-loop first, closed-loop later | Button injection is proven and sufficient for TOU; display decoding is complex and can wait | -- Pending |
| AQY212EH specifically | DIP-4 package fits breadboard, 60V/500mA rating adequate, 0.2 ohm on-resistance acceptable for analog line | -- Pending |
| 0x73 for "9" (not GS510SZ 0x7B) | VS300FL4 draws "9" without bottom segment; confirmed via ladder capture walking setpoint 95-90 | Confirmed 2026-03-20 |
| Interrupt-driven GPIO over UART for ESPHome | Protocol is synchronous clock+data, not async UART; UART approach produces garbage | Decided, not yet implemented |

---
*Last updated: 2026-03-13 after initialization*
