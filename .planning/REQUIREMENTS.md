# Requirements: Tubtron

**Defined:** 2026-03-13
**Core Value:** The tub automatically lowers its setpoint during on-peak hours and raises it before evening use -- no human involvement required.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Button Injection

- [x] **BUTN-01**: User can set target temperature via HA number entity (80-104°F, no unit conversion)
- [x] **BUTN-02**: ESP32 simulates Temp Up/Down button presses via photorelays with no phantom presses
- [x] **BUTN-03**: Probe+cache sequence: probe finds current setpoint, counts delta presses to target (re-home sequence as fallback)
- [x] **BUTN-04**: Firmware clamps temperature range to 80-104F (CPSC safety limit)
- [x] **BUTN-05**: No interference or phantom presses during button simulation (galvanic isolation, short leads, decoupling caps on analog lines)

### Connectivity

- [x] **CONN-01**: ESP32 firmware supports OTA updates without physical access
- [x] **CONN-02**: WiFi auto-reconnects with fallback AP mode for recovery
- [x] **CONN-03**: All button commands and state changes are logged (ESPHome logger + HA state history)

### Display Reading

- [x] **DISP-01**: ESP32 decodes RS-485 display stream to read current water temperature (lookup table fully confirmed via ladder capture 2026-03-20)
- [x] **DISP-02**: Current temperature populates a plain HA sensor entity (integer °F, no unit conversion -- climate entity removed due to forced F→C conversion bug)
- [ ] **DISP-03**: Drift detection compares display reading vs expected setpoint and auto-corrects on mismatch (firmware logic exists; blocked on HA entity fix)

### Energy

- [ ] **ENRG-01**: HA tracks energy cost savings via utility_meter and template sensors

## v2 Requirements

Requirements for Closed-Loop Trust milestone (v2.0).

### Command Reliability

- [x] **CMD-01**: Failed button presses retry automatically with exponential backoff (5s/15s/45s), up to 3 retries (4 total attempts), with press budget enforcement (N+2 presses per attempt)
- [x] **CMD-02**: If detected setpoint disagrees with commanded setpoint for >2 minutes while injection is idle, HA fires a persistent notification (drift detection)

### Safety and Power

- [ ] **SAFE-01**: Graduated thermal runaway response (warning, partial reduction, floor drop)
- [ ] **SAFE-02**: TOU-runaway oscillation prevention (runaway cooldown flag blocks TOU raise)
- [ ] **SAFE-03**: Stale data gating (refuse to act on last-known values when ESP32 offline)
- [ ] **PWR-01**: Independent heater state via Enphase power consumption (4kW step detection)

### Data Pipeline

- [ ] **DATA-01**: REST API history export from HA to dev machine
- [ ] **DATA-02**: analyze_heating.py ingests REST API JSON directly (no SQLite dependency)

### Extras

- **EXTR-01**: Lights/Jets control via additional photorelays on Pin 3/Pin 7
- **EXTR-02**: Board-powered operation via B0505S-1W isolated DC-DC (eliminate USB power)
- **EXTR-03**: Freeze protection awareness (parse OH/ICE display codes, suppress automation during protection events)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
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
| DISP-01 | Phase 1 | Complete |
| BUTN-02 | Phase 1 | Complete |
| BUTN-03 | Phase 1 | Complete |
| BUTN-04 | Phase 1 | Complete |
| BUTN-05 | Phase 1 | Complete |
| CONN-01 | Phase 1 | Complete |
| CONN-02 | Phase 1 | Complete |
| CONN-03 | Phase 1 | Complete |
| BUTN-01 | Phase 2 | Complete |
| DISP-02 | Phase 2 | Complete |
| DISP-03 | Phase 2 | Pending |
| ENRG-01 | Phase 2 | Pending |
| CMD-01 | Phase 4 | Complete |
| CMD-02 | Phase 4 | Complete |
| SAFE-01 | Phase 5 | Pending |
| SAFE-02 | Phase 5 | Pending |
| SAFE-03 | Phase 5 | Pending |
| PWR-01 | Phase 5 | Pending |
| DATA-01 | Phase 6 | Pending |
| DATA-02 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 12 total
- v2 requirements: 8 total
- Mapped to phases: 20
- Unmapped: 0

---
*Requirements defined: 2026-03-13*
*Last updated: 2026-04-03 -- Phase 1 complete (DISP-01, BUTN-02-05, CONN-01-03); BUTN-01/DISP-02 revised: climate entity removed, sensor+number replacement pending; BUTN-03 revised: probe+cache implemented (not re-home)*
