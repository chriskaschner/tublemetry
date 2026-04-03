# Roadmap: Tubtron

## Overview

Tubtron delivers hot tub TOU automation in three phases. Phase 1 built both the read path (RS-485 display decoding) and write path (button injection via photorelays) together — the two were developed as a single MVP. Phase 2 fixes the architecture: the ESPHome climate entity (which forces a broken F→C→F conversion chain) is replaced with a sensor + number entity pair, restoring HA temperature reporting and setpoint control. Phase 3 publishes the protocol findings and ESPHome component for the community.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: RS-485 Display Reading + Button Injection MVP** - Protocol reverse-engineering, display stream decoding, button injection via photorelays, probe+cache setpoint control, OTA/WiFi, TOU schedule in HA
- [ ] **Phase 2: Architecture Fix + HA Integration** - Replace climate entity with sensor+number (fix F→C conversion bug), restore HA temperature reporting and setpoint control, fix TOU automation, add version reporting
- [ ] **Phase 3: Community Contribution** - Publish protocol documentation and ESPHome component for VS-series hot tub community

## Phase Details

### Phase 1: RS-485 Display Reading + Button Injection MVP
**Goal**: ESP32 decodes the Balboa VS300FL4 display stream and simulates button presses via photorelays — system is physically wired, live, and self-managing via TOU schedule
**Depends on**: Nothing (first phase)
**Requirements**: DISP-01, BUTN-02, BUTN-03, BUTN-04, BUTN-05, CONN-01, CONN-02, CONN-03
**Status**: Complete (2026-03-30)
**Plans:** 3 plans (3 complete)

Plans:
- [x] 01-01-PLAN.md -- Python decode library: test infrastructure, 7-segment decoder, frame parser, display state machine (TDD)
- [x] 01-02-PLAN.md -- ESPHome external component: C++ port of decode logic, climate entity, diagnostic sensors, YAML config
- [x] 01-03-PLAN.md -- Gap closure: fix requirement statuses, add structural YAML tests, prepare ladder capture tooling

### Phase 2: Architecture Fix + HA Integration
**Goal**: Current water temperature appears in HA as a plain sensor (°F, no conversion); user can set target temperature from HA via a number entity; TOU automation fires correctly with °F values
**Depends on**: Phase 1 (hardware live, firmware deployed)
**Requirements**: BUTN-01, DISP-02
**Success Criteria** (what must be TRUE):
  1. `sensor.tublemetry_hot_tub_temperature` exists in HA and shows current water temperature as an integer °F value with no unit conversion
  2. `number.tublemetry_hot_tub_setpoint` exists in HA, accepts 80-104°F in 1° steps, and triggers button injection sequence on change
  3. TOU automation `ha/tou_automation.yaml` fires using °F values (104, 102, 98, 96) against the number entity
  4. Component version string is published to a text sensor in HA on boot
  5. `esphome compile tublemetry.yaml` succeeds with no climate component; all existing tests pass
**Plans:** 2/3 plans executed

Plans:
- [x] 02-01-PLAN.md -- C++ + codegen layer: TublemetrySetpoint class, number.py, temperature sensor in sensor.py, AUTO_LOAD update, tublemetry_display.h/.cpp wiring
- [x] 02-02-PLAN.md -- YAML + HA config: add sensor/number entries to tublemetry.yaml, fix tou_automation.yaml with number entity and degF values
- [ ] 02-03-PLAN.md -- Tests: extend test_esphome_yaml.py with sensor/number entity checks, create test_number_entity.py for range and TOU automation validation

### Phase 3: Community Contribution
**Goal**: Protocol findings and ESPHome component are published in a form the community can use — documented, tested, and referenced from the relevant ESPHome/Balboa community threads
**Depends on**: Phase 2 (stable architecture before publishing)
**Requirements**: None (publication milestone)
**Success Criteria**:
  1. Protocol documentation published (RJ45 pinout, clock+data framing, 7-segment lookup table, VS300FL4 quirks vs GS510SZ reference)
  2. ESPHome external component usable by others (clean YAML interface, no hardcoded assumptions)
  3. Community threads updated with findings (ESPHome forum, relevant GitHub issues)
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. RS-485 Display Reading + Button Injection MVP | 3/3 | Complete | 2026-03-30 |
| 2. Architecture Fix + HA Integration | 2/3 | In Progress|  |
| 3. Community Contribution | 0/? | Not started | - |
