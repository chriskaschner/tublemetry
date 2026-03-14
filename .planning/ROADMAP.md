# Roadmap: Tubtron

## Overview

Tubtron delivers hot tub TOU automation in two phases. Phase 1 builds the read path: an ESP32 decodes the RS-485 display stream to surface current water temperature in a HA climate entity -- this alone delivers temperature monitoring and validates the protocol. Phase 2 adds the write path: button injection via photorelays enables automated setpoint changes, and because the read path already exists, closed-loop verification, drift correction, and energy tracking work from day one. Reading the display unlocks everything; button injection on top of it is closed-loop from the start.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: RS-485 Display Reading** - Temperature ladder capture, display stream decoding, current water temperature in HA climate entity
- [ ] **Phase 2: Button Injection + Closed-Loop Control** - Photorelay button simulation, re-home sequence, drift correction, connectivity resilience, energy cost tracking

## Phase Details

### Phase 1: RS-485 Display Reading
**Goal**: User can see current hot tub water temperature in Home Assistant -- read from the tub's display stream via RS-485, not guessed or assumed
**Depends on**: Nothing (first phase); physical tub access + RS-485 adapter required for temperature ladder capture
**Requirements**: DISP-01, DISP-02
**Success Criteria** (what must be TRUE):
  1. Temperature ladder captured at 5+ known temperatures, resolving the 72-solution 7-segment encoding ambiguity
  2. ESP32 decodes the Pin 5 RS-485 display stream in real time and extracts the current water temperature
  3. HA climate entity displays the current water temperature (read-only -- no setpoint control yet)
**Plans:** 2 plans

Plans:
- [ ] 01-01-PLAN.md -- Python decode library: test infrastructure, 7-segment decoder, frame parser, display state machine (TDD)
- [ ] 01-02-PLAN.md -- ESPHome external component: C++ port of decode logic, climate entity, diagnostic sensors, YAML config

### Phase 2: Button Injection + Closed-Loop Control
**Goal**: User can set hot tub temperature from Home Assistant with closed-loop verification -- the system writes setpoints via button injection and reads confirmation via display decoding, with automatic drift correction
**Depends on**: Phase 1 (display reading must work before closed-loop control is meaningful)
**Requirements**: BUTN-01, BUTN-02, BUTN-03, BUTN-04, BUTN-05, CONN-01, CONN-02, CONN-03, DISP-03, ENRG-01
**Success Criteria** (what must be TRUE):
  1. User can set a target temperature (80-104F) from the HA climate entity and the tub's setpoint changes to match
  2. Re-home sequence reliably reaches the correct temperature from any starting point (no accumulated drift after repeated cycles)
  3. No phantom presses or interference occur during or between button simulation sequences
  4. If the displayed temperature diverges from the expected setpoint (manual override, missed press, power cycle), the system detects the mismatch and auto-corrects
  5. Firmware can be updated over WiFi (OTA) and ESP32 reconnects automatically after network interruptions with fallback AP mode
  6. HA dashboard shows cumulative energy cost savings from TOU schedule via utility_meter and template sensors
**Plans**: TBD

Plans:
- [ ] 02-01: TBD
- [ ] 02-02: TBD
- [ ] 02-03: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. RS-485 Display Reading | 2/2 | Complete (awaiting human-verify checkpoint) | 2026-03-14 |
| 2. Button Injection + Closed-Loop Control | 0/3 | Not started | - |
