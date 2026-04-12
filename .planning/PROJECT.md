# Tubtron

## What This Is

A hot tub automation system that controls a Balboa VS300FL4 controller via ESP32 and Home Assistant. It simulates physical button presses through photorelays to adjust temperature setpoints on a Time-of-Use electricity schedule, saving ~$10/month on MGE Rg-2A rates without manual intervention.

## Core Value

The tub automatically lowers its setpoint during on-peak hours and raises it before evening use -- no human involvement required.

## Current Milestone: v2.0 Closed-Loop Trust

**Goal:** Make the setpoint command path bulletproof and observable so TOU automation can run unattended without silent drift.

**Target features:**
- Command reliability: tuned press timing, retry on verification failure, success/failure surfaced to HA
- Observable data pipeline: time-series data accessible from dev machine, not locked in HA SQLite on RPi
- Power-based heater validation: use Enphase whole-home power monitoring as independent heater ground truth
- Safety hardening: apply embedded safety paradigms (sensor fusion, command-verify-retry, defensive coding)

## Requirements

### Validated

- Confirmed RJ45 pinout: +5V (pin 1), GND (pin 4), analog button lines (pins 2/3/7/8), RS-485 data (pins 5/6)
- Confirmed button simulation works: bridging +5V to button pin changes setpoint
- Confirmed synchronous clock+data protocol (NOT RS-485 UART): Pin 6=clock, Pin 5=data, 24 bits/frame at 60Hz
- Full 7-segment lookup table confirmed via ladder capture (2026-03-20): all digits 0-9, mode letters E/c/L/t/H
- VS300FL4 uses 0x73 for "9" (no bottom segment), differs from GS510SZ reference (0x7B)
- ESP32 reads display, injects button presses, exposes sensor+number entities to HA via ESPHome API
- Probe+cache setpoint control (direct-delta, no sweep) with verification and timeout
- TOU automation drafted and running (6 time triggers, weekday/weekend schedule)
- Thermal runaway protection: detects temp > setpoint + 2F for 5 min, logs, disables TOU, drops to 80F
- Auto-refresh (unsolicited down+up press pairs) removed -- caused setpoint drift via lost presses

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
| Number entity over climate entity | Climate entity forces F->C->F conversion chain, corrupts temperature display | Confirmed good |
| Probe+cache over re-home sweep | Direct delta presses (e.g. 10 up for 94->104) vs 49 for re-home; user preference | Confirmed good |
| Remove auto-refresh keepalive | Unsolicited down+up press pairs every 5 min caused setpoint drift from lost presses | Confirmed good |
| Thermal runaway automation | Safety net: detects overshoot, logs, disables TOU, drops setpoint to floor | Confirmed good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check -- still the right priority?
3. Audit Out of Scope -- reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-12 after milestone v2.0 start*
