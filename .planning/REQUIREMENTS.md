# Requirements: Tubtron

**Defined:** 2026-03-13
**Core Value:** The tub automatically lowers its setpoint during on-peak hours and raises it before evening use -- no human involvement required.

## v1 Requirements

Requirements from milestone v1.0. Shipped and validated.

### Button Injection

- [x] **BUTN-01**: User can set target temperature via HA number entity (80-104F, no unit conversion)
- [x] **BUTN-02**: ESP32 simulates Temp Up/Down button presses via photorelays with no phantom presses
- [x] **BUTN-03**: Probe+cache sequence: probe finds current setpoint, counts delta presses to target
- [x] **BUTN-04**: Firmware clamps temperature range to 80-104F (CPSC safety limit)
- [x] **BUTN-05**: No interference or phantom presses during button simulation (galvanic isolation)

### Connectivity

- [x] **CONN-01**: ESP32 firmware supports OTA updates without physical access
- [x] **CONN-02**: WiFi auto-reconnects with fallback AP mode for recovery
- [x] **CONN-03**: All button commands and state changes are logged (ESPHome logger + HA state history)

### Display Reading

- [x] **DISP-01**: ESP32 decodes display stream to read current water temperature (lookup table confirmed via ladder capture)
- [x] **DISP-02**: Current temperature populates a plain HA sensor entity (integer F, no unit conversion)

## v2 Requirements

Requirements for milestone v2.0: Closed-Loop Trust.

### Command Reliability

- [ ] **CMD-01**: ButtonInjector retries up to 2 times on verification timeout with exponential backoff, enforcing a press budget of max N+2 presses for an N-degree delta
- [ ] **CMD-02**: Setpoint drift detection compares detected setpoint vs commanded setpoint and alerts on persistent mismatch (>2 min disagreement)

### Power Validation

- [ ] **PWR-01**: HA template binary sensor derives heater on/off state from Enphase whole-home power consumption using a configurable watt threshold (~4kW step detection)

### Data Pipeline

- [ ] **DATA-01**: Python script pulls HA entity history via REST API and outputs CSV files on the dev machine
- [ ] **DATA-02**: analyze_heating.py accepts REST API JSON input as an alternative to the SQLite path

### Safety Hardening

- [ ] **SAFE-01**: Thermal runaway automation uses graduated response (log-only for small overshoot, partial setpoint reduction, nuclear floor drop) instead of immediate nuclear response
- [ ] **SAFE-02**: TOU automation checks a runaway cooldown flag before raising setpoint, preventing TOU-runaway oscillation
- [ ] **SAFE-03**: Safety automations detect stale ESP32 data (disconnect/unavailable) and gate actions on data freshness

## v2.1+ Requirements

Deferred to future release. Tracked but not in current roadmap.

### Command Reliability

- **CMD-03**: Injection result + attempt count sensors exposed to HA
- **CMD-04**: HA escalation automation on retry exhaustion

### Power Validation

- **PWR-02**: Heater mismatch detection (display bit vs power disagree >2 min)
- **PWR-03**: 2-of-3 voting (power + status bit + temp derivative)

### Data Pipeline

- **DATA-03**: 30-day recorder retention for hot-tub entities

### Safety Hardening

- **SAFE-04**: Weekly safety heartbeat test
- **SAFE-05**: Automation watchdog monitoring runaway enablement

### Other

- **DISP-03**: Drift detection compares display reading vs expected setpoint and auto-corrects on mismatch
- **ENRG-01**: HA tracks energy cost savings via utility_meter and template sensors
- **EXTR-01**: Lights/Jets control via additional photorelays
- **EXTR-02**: Board-powered operation via B0505S-1W isolated DC-DC
- **EXTR-03**: Freeze protection awareness (parse OH/ICE display codes)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Kalman filter / formal sensor fusion | Only 2-3 signals; simple threshold/voting is sufficient and debuggable |
| InfluxDB / external time-series DB | Unnecessary infrastructure on RPi4 SD card; REST API + SCP covers needs |
| MQTT bridge | ESPHome native API covers all needs; adding MQTT adds complexity for no benefit |
| Thermal model seasonal calibration | Needs a full season of data; defer to summer/fall 2026 |
| Community protocol publication | Orthogonal to closed-loop trust; separate milestone |
| ESPHome set_retry API | Deprecated 2026.2.0, removed 2026.8.0; use hand-rolled retry in ButtonInjector |
| RS-485 command injection | No digital command channel exists on VS-series |
| PID control on ESP32 | Board has its own thermostat; dual control loop would fight itself |
| Board replacement | BP-series costs $400-800, defeats cost-saving purpose |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| BUTN-01 | Phase 2 | Complete |
| BUTN-02 | Phase 1 | Complete |
| BUTN-03 | Phase 1 | Complete |
| BUTN-04 | Phase 1 | Complete |
| BUTN-05 | Phase 1 | Complete |
| CONN-01 | Phase 1 | Complete |
| CONN-02 | Phase 1 | Complete |
| CONN-03 | Phase 1 | Complete |
| DISP-01 | Phase 1 | Complete |
| DISP-02 | Phase 2 | Complete |
| CMD-01 | Phase 4 | Pending |
| CMD-02 | Phase 4 | Pending |
| PWR-01 | Phase 5 | Pending |
| DATA-01 | Phase 6 | Pending |
| DATA-02 | Phase 6 | Pending |
| SAFE-01 | Phase 5 | Pending |
| SAFE-02 | Phase 5 | Pending |
| SAFE-03 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 10 total, 10 complete
- v2 requirements: 8 total, 8 mapped to phases
- Unmapped: 0

---
*Requirements defined: 2026-03-13*
*Last updated: 2026-04-12 after v2.0 roadmap creation*
