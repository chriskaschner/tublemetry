# Roadmap: Tubtron

## Overview

Tubtron delivers hot tub TOU automation across two milestones. v1.0 built the hardware integration (display decoding, button injection, HA entity architecture) in Phases 1-3. v2.0 (Closed-Loop Trust) makes the system bulletproof for unattended operation: Phase 4 adds firmware-level command retry with verification and drift detection, Phase 5 hardens safety automations with graduated response, stale-data gating, and independent power-based heater validation, and Phase 6 builds a dev-machine data pipeline for systematic analysis.

## Milestones

- v1.0 MVP - Phases 1-3 (in progress)
- v2.0 Closed-Loop Trust - Phases 4-6 (planned)

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

<details>
<summary>v1.0 MVP (Phases 1-3)</summary>

- [x] **Phase 1: RS-485 Display Reading + Button Injection MVP** - Protocol reverse-engineering, display stream decoding, button injection via photorelays, probe+cache setpoint control, OTA/WiFi, TOU schedule in HA
- [x] **Phase 2: Architecture Fix + HA Integration** - Replace climate entity with sensor+number (fix F-to-C conversion bug), restore HA temperature reporting and setpoint control, fix TOU automation, add version reporting
- [ ] **Phase 3: Community Contribution** - Publish protocol documentation and ESPHome component for VS-series hot tub community

</details>

### v2.0 Closed-Loop Trust

- [ ] **Phase 4: Command Reliability** - Firmware retry loop with verification, press-budget enforcement, and HA-side setpoint drift detection
- [ ] **Phase 5: Safety and Power Validation** - Graduated thermal runaway response, TOU-runaway oscillation prevention, stale-data gating, and Enphase power-based heater validation
- [ ] **Phase 6: Data Pipeline** - REST API history export and analysis scripts on dev machine

## Phase Details

<details>
<summary>v1.0 MVP Phase Details (Phases 1-3)</summary>

### Phase 1: RS-485 Display Reading + Button Injection MVP
**Goal**: ESP32 decodes the Balboa VS300FL4 display stream and simulates button presses via photorelays -- system is physically wired, live, and self-managing via TOU schedule
**Depends on**: Nothing (first phase)
**Requirements**: DISP-01, BUTN-02, BUTN-03, BUTN-04, BUTN-05, CONN-01, CONN-02, CONN-03
**Status**: Complete (2026-03-30)
**Plans:** 3 plans (3 complete)

Plans:
- [x] 01-01-PLAN.md -- Python decode library: test infrastructure, 7-segment decoder, frame parser, display state machine (TDD)
- [x] 01-02-PLAN.md -- ESPHome external component: C++ port of decode logic, climate entity, diagnostic sensors, YAML config
- [x] 01-03-PLAN.md -- Gap closure: fix requirement statuses, add structural YAML tests, prepare ladder capture tooling

### Phase 2: Architecture Fix + HA Integration
**Goal**: Current water temperature appears in HA as a plain sensor (deg F, no conversion); user can set target temperature from HA via a number entity; TOU automation fires correctly with deg F values
**Depends on**: Phase 1 (hardware live, firmware deployed)
**Requirements**: BUTN-01, DISP-02
**Success Criteria** (what must be TRUE):
  1. `sensor.tublemetry_hot_tub_temperature` exists in HA and shows current water temperature as an integer deg F value with no unit conversion
  2. `number.tublemetry_hot_tub_setpoint` exists in HA, accepts 80-104 deg F in 1 deg steps, and triggers button injection sequence on change
  3. TOU automation `ha/tou_automation.yaml` fires using deg F values (104, 102, 98, 96) against the number entity
  4. Component version string is published to a text sensor in HA on boot
  5. `esphome compile tublemetry.yaml` succeeds with no climate component; all existing tests pass
**Plans:** 3 plans (3 complete)

Plans:
- [x] 02-01-PLAN.md -- C++ + codegen layer: TublemetrySetpoint class, number.py, temperature sensor in sensor.py, AUTO_LOAD update, tublemetry_display.h/.cpp wiring
- [x] 02-02-PLAN.md -- YAML + HA config: add sensor/number entries to tublemetry.yaml, fix tou_automation.yaml with number entity and deg F values
- [x] 02-03-PLAN.md -- Tests: extend test_esphome_yaml.py with sensor/number entity checks, create test_number_entity.py for range and TOU automation validation

### Phase 3: Community Contribution
**Goal**: Protocol findings and ESPHome component are published in a form the community can use -- documented, tested, and referenced from the relevant ESPHome/Balboa community threads
**Depends on**: Phase 2 (stable architecture before publishing)
**Requirements**: None (publication milestone)
**Success Criteria**:
  1. Protocol documentation published (RJ45 pinout, clock+data framing, 7-segment lookup table, VS300FL4 quirks vs GS510SZ reference)
  2. ESPHome external component usable by others (clean YAML interface, no hardcoded assumptions)
  3. Community threads updated with findings (ESPHome forum, relevant GitHub issues)
**Plans**: TBD

</details>

### v2.0 Closed-Loop Trust

#### Phase 4: Command Reliability
**Goal**: Button injection commands self-verify and self-correct -- failed presses retry automatically, and persistent setpoint disagreement is surfaced to the user
**Depends on**: Phase 2 (number entity and button injection must be stable)
**Requirements**: CMD-01, CMD-02
**Success Criteria** (what must be TRUE):
  1. When a button press fails to register (display does not reflect expected change), the ESP32 retries up to 2 times with exponential backoff -- no manual intervention needed
  2. Total button presses for any setpoint change never exceed N+2 for an N-degree delta (press budget enforcement prevents runaway overshoot)
  3. If the detected setpoint disagrees with the commanded setpoint for more than 2 minutes, HA fires a persistent notification alerting the user
  4. After a command sequence completes (success or retry-exhausted), the outcome is observable in HA entity state
**Plans**: TBD

#### Phase 5: Safety and Power Validation
**Goal**: The system can run unattended for weeks without silent failure -- thermal runaway responds proportionally, TOU and runaway do not fight each other, stale data is detected, and an independent power signal validates heater state
**Depends on**: Phase 4 (command path must be reliable before adding safety layers that depend on it)
**Requirements**: SAFE-01, SAFE-02, SAFE-03, PWR-01
**Success Criteria** (what must be TRUE):
  1. Thermal runaway automation uses graduated response: small overshoot (2-4F) logs a warning without acting, moderate overshoot triggers partial setpoint reduction, only severe overshoot drops to floor
  2. After a thermal runaway event, TOU automation does not raise the setpoint until the runaway cooldown flag clears -- no oscillation loop
  3. If the ESP32 goes offline or reports stale data, safety automations refuse to act on the last-known values and alert the user instead
  4. A binary sensor in HA shows heater on/off state derived from Enphase whole-home power consumption (4kW step detection), independent of the display status bit
**Plans**: TBD

#### Phase 6: Data Pipeline
**Goal**: Operational data from HA is accessible on the dev machine for systematic analysis without SSH-ing into the RPi or copying SQLite files
**Depends on**: Phase 4 (command result data must exist before it is worth exporting)
**Requirements**: DATA-01, DATA-02
**Success Criteria** (what must be TRUE):
  1. Running a Python script on the dev machine produces CSV files containing recent HA entity history (temperature, setpoint, heater state, command results)
  2. `analyze_heating.py` can ingest data from the REST API JSON response directly, without requiring the SQLite database file
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. RS-485 Display Reading + Button Injection MVP | v1.0 | 3/3 | Complete | 2026-03-30 |
| 2. Architecture Fix + HA Integration | v1.0 | 3/3 | Complete | -- |
| 3. Community Contribution | v1.0 | 0/? | Not started | - |
| 4. Command Reliability | v2.0 | 0/? | Not started | - |
| 5. Safety and Power Validation | v2.0 | 0/? | Not started | - |
| 6. Data Pipeline | v2.0 | 0/? | Not started | - |
