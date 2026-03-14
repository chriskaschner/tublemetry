# Requirements: Tubtron

**Defined:** 2026-03-13
**Core Value:** The tub automatically lowers its setpoint during on-peak hours and raises it before evening use -- no human involvement required.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Button Injection

- [ ] **BUTN-01**: User can set target temperature via HA climate entity
- [ ] **BUTN-02**: ESP32 simulates Temp Up/Down button presses via photorelays with no phantom presses
- [ ] **BUTN-03**: Re-home sequence slams 25x to floor (80F) then counts up to target temperature
- [ ] **BUTN-04**: Firmware clamps temperature range to 80-104F (CPSC safety limit)
- [ ] **BUTN-05**: No interference or phantom presses during button simulation (galvanic isolation, short leads, decoupling caps on analog lines)

### Connectivity

- [ ] **CONN-01**: ESP32 firmware supports OTA updates without physical access
- [ ] **CONN-02**: WiFi auto-reconnects with fallback AP mode for recovery
- [ ] **CONN-03**: All button commands and state changes are logged (ESPHome logger + HA state history)

### Display Reading

- [ ] **DISP-01**: ESP32 decodes RS-485 display stream to read current water temperature -- In Progress: firmware ready, hardware verification pending, lookup table unverified (17/20 entries)
- [ ] **DISP-02**: Current temperature populates HA climate entity (full thermostat card with current + target) -- In Progress: climate entity defined, hardware integration pending
- [ ] **DISP-03**: Drift detection compares display reading vs expected setpoint and auto-corrects on mismatch

### Energy

- [ ] **ENRG-01**: HA tracks energy cost savings via utility_meter and template sensors

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Extras

- **EXTR-01**: Lights/Jets control via additional photorelays on Pin 3/Pin 7
- **EXTR-02**: Board-powered operation via B0505S-1W isolated DC-DC (eliminate USB power)
- **EXTR-03**: Freeze protection awareness (parse OH/ICE display codes, suppress automation during protection events)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| TOU schedule automation | User handles directly in HA automations |
| RS-485 command injection | No digital command channel exists on VS-series; panel is dumb analog |
| PID control on ESP32 | Board has its own thermostat; dual control loop would fight itself |
| Cloud connectivity | ESPHome native API is local-only, faster, and more reliable |
| Mobile app / standalone UI | HA already provides mobile app, dashboards, voice control |
| Water quality monitoring | Separate project; requires dedicated probes and calibration |
| ML/usage pattern prediction | Fixed TOU schedule is deterministic; ML is over-engineering |
| Board replacement | BP-series costs $400-800, defeats cost-saving purpose |
| Community publication | Phase 3 milestone, separate from v1 scope |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DISP-01 | Phase 1 | In Progress |
| DISP-02 | Phase 1 | In Progress |
| BUTN-01 | Phase 2 | Pending |
| BUTN-02 | Phase 2 | Pending |
| BUTN-03 | Phase 2 | Pending |
| BUTN-04 | Phase 2 | Pending |
| BUTN-05 | Phase 2 | Pending |
| CONN-01 | Phase 2 | Pending |
| CONN-02 | Phase 2 | Pending |
| CONN-03 | Phase 2 | Pending |
| DISP-03 | Phase 2 | Pending |
| ENRG-01 | Phase 2 | Pending |

**Coverage:**
- v1 requirements: 12 total
- Mapped to phases: 12
- Unmapped: 0

---
*Requirements defined: 2026-03-13*
*Last updated: 2026-03-14 -- DISP-01/DISP-02 statuses revised per 01-VERIFICATION.md gap analysis (firmware ready, hardware verification pending)*
