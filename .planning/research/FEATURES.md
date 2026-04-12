# Feature Research

**Domain:** Closed-loop embedded control for hot tub automation (command reliability, observability, power validation, safety hardening, signal processing)
**Researched:** 2026-04-12
**Confidence:** MEDIUM-HIGH (well-established patterns across all five domains; Enphase-specific integration details are HIGH confidence from official HA docs)

## Feature Landscape

### Table Stakes (System Must Have These for Unattended Operation)

Features that are required before the TOU automation can be called "trustworthy enough to run unsupervised."

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Command-verify with bounded retry** | Current system fires-and-forgets setpoint changes. A TIMEOUT result means the setpoint may be wrong, but nothing retries. Unattended operation requires automatic recovery. | MEDIUM | Already have IDLE->PROBE->ADJUST->VERIFY->COOLDOWN state machine. Need to add a RETRY phase with counter (max 2-3 attempts) and exponential delay between attempts. Pattern is well-established in industrial control: command, read back, retry on mismatch, enter safe state after max retries. |
| **Command result surfaced to HA** | TOU automation calls `number.set_value` and has zero visibility into whether it worked. Must know success/failure to decide whether to retry or alert. | LOW | `injection_state_sensor_` text sensor already exists and publishes phase. Need a persistent `last_result` sensor (success/timeout/failed) and a counter pair (success_count, total_count) visible in HA. Wiring already exists, just needs entity exposure. |
| **Setpoint drift detection** | If a physical button press (person at tub) or lost press changes the real setpoint, the system should detect the mismatch. Without this, TOU silently operates on wrong assumptions. | MEDIUM | The `detected_setpoint_sensor` already captures display-flashed setpoints. Need an automation that compares `detected_setpoint` vs `commanded_setpoint` and fires an alert on mismatch. Logic lives in HA, not ESP32. |
| **Stability filtering for display decode** | 60Hz frame decode is noisy. Misreads cause phantom temperature jumps that confuse verification and thermal models. | LOW | Already implemented: `STABLE_THRESHOLD = 3` requires 3 consecutive identical frames. This is the right approach. May need tuning (raise to 5?) but pattern is correct. No new code, just validation. |
| **Watchdog and safe-mode recovery** | ESP32 hangs or WiFi drops leave the tub uncontrolled. Must self-recover. | LOW | Already implemented in ESPHome config: `reboot_timeout: 10min` (WiFi), `reboot_timeout: 15min` (API), `safe_mode: num_attempts: 10`. This is the ESPHome-native equivalent of a task-level watchdog. Already table-stakes complete. |

### Differentiators (Make the System Genuinely Trustworthy)

Features that transform this from "automation that mostly works" to "automation you can trust and observe."

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Time-series data export to dev machine** | The existing `analyze_heating.py` script already queries the HA SQLite DB directly via SCP. Formalizing this into a repeatable pipeline (cron + scp + analysis) removes the need for InfluxDB or any new infrastructure. | LOW | Use REST API `/api/history/period/{ts}?filter_entity_id=...&minimal_response&no_attributes` with a Python script on the dev Mac. Pulls just the entities needed (temperature, setpoint, heater, power) over the network. No Samba, no InfluxDB. Alternatively, keep the SCP+SQLite approach from `analyze_heating.py` -- it already works and adds zero load to HA. |
| **Enphase power as heater ground truth** | Independent confirmation that the heater is actually running (via 4kW step in whole-home power), cross-referenced against the display-decoded heater binary sensor. Catches: display decode bug says heater is off but it's actually on (thermal runaway not detected). | MEDIUM | Enphase Envoy core integration exposes `wattsNow` via `/ivp/meters/readings` (64ms response, real-time). A 4kW resistive heater produces a clean, flat ~4000W step -- trivial to detect via threshold. HA template sensor: `power > 3500` = heater_on. Compare against `binary_sensor.tublemetry_hot_tub_heater`. Agreement = confidence; disagreement = alert. |
| **HA-side retry automation** | If ESP32 reports TIMEOUT after max retries, HA automation waits 60s and tries the whole `number.set_value` call again. Catches transient failures (WiFi hiccup during injection, display in mode-change state). | LOW | Simple HA automation: trigger on `injection_state` = "timeout", condition: retry_count < 3, action: wait 60s, call `number.set_value` again. Uses `input_number` as retry counter, resets on success. |
| **Command success rate dashboard** | Track and display the percentage of setpoint commands that succeed. Degradation over time signals wiring issues, timing drift, or hardware wear. | LOW | Template sensor: `success_count / total_count * 100`. Surfaced on dashboard. Threshold alert if rate drops below 90%. All data already tracked in ESP32 `ButtonInjector` counters. |
| **Thermal model with outdoor temp correlation** | `analyze_heating.py` already captures outdoor temp in heating event analysis. Formalizing this into the thermal model improves preheat ETA accuracy across seasons. | LOW | The script already does this. Needs the outdoor temp sensor entity (`sensor.outdoor_temperature`) included in the exported data. Plot correlation. Use slope to adjust preheat lead time by season. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that sound good but create problems in this specific system.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **InfluxDB / TimescaleDB for time-series** | "Proper" time-series database, Grafana dashboards, infinite retention. | Adds a database server to the RPi4 (RAM/SD-card pressure), requires ongoing maintenance, and the RPi is already running HA OS. The existing SQLite DB + SCP workflow already works. Adding InfluxDB solves a problem you do not have. | Keep using REST API or SCP + SQLite for analysis on dev Mac. If you outgrow this (>1 year of data at current volume), revisit then. The HA long-term statistics aggregation (hourly) handles retention natively. |
| **Circuit-level power monitoring (Emporia Vue)** | Dedicated CT clamp on the hot tub breaker gives exact heater power, not inferred from whole-home. | Requires electrician for panel install, $150-200 hardware, another integration to maintain. The 4kW heater step is the largest single load in most homes -- whole-home Enphase data detects it reliably via simple threshold. Dedicated monitoring is warranted if whole-home proves ambiguous (second large 240V load on same breaker). | Start with Enphase whole-home power threshold. Only add dedicated CT if the 4kW step is obscured by other loads. |
| **Auto-retry with no limit / aggressive retry** | "Just keep trying until it works." | Infinite retry can cause setpoint oscillation. If the Balboa controller is in a mode where presses are not accepted (filter cycle, error state, user interaction), hammering buttons makes things worse. Lost presses during aggressive retry were the exact failure mode that killed auto-refresh. | Bounded retry: max 3 attempts with increasing delay (5s, 15s, 60s). After max retries, log, alert, stop. Human investigates. |
| **MQTT bridge for data export** | Publish all sensor data to MQTT broker, consume from external tools. | Adds MQTT broker infrastructure. ESPHome natively uses the HA API, not MQTT. Adding MQTT means dual-publishing, potential state sync issues, and another service to maintain on the RPi. | Use the HA REST API or WebSocket API from the dev machine. These are already available, authenticated, and maintained by HA core. |
| **Full IEC 61508 SIL compliance** | "Do it right" with formal hazard analysis, redundant processors, certified software. | This is a hot tub. SIL 1 alone requires formal documentation, V&V lifecycle, and certified tools. The cost/effort ratio is absurd for a $6 BOM hobby project. The real hazard (thermal runaway) is already mitigated. | Apply IEC 61508 *principles* without formal compliance: identify hazards, design safe states, bound failure modes, test fault scenarios. The thermal runaway automation is exactly this approach. |
| **Sensor fusion with Kalman filter on ESP32** | "Use proper signal processing" for temperature. | The temperature sensor reads at 60Hz via display decode, resolution is 1 degF, and the physical process (300 gallons of water) changes at ~0.1 degF/min. The signal is already oversampled by 3+ orders of magnitude. A Kalman filter adds CPU load and complexity for zero practical improvement. The stability filter (3 consecutive identical frames) is the correct tool. | Keep the stability filter. If noise problems emerge, increase `STABLE_THRESHOLD` to 5 or add ESPHome `median` filter on the temperature sensor. Both are trivial YAML changes. |
| **WebSocket streaming for real-time monitoring** | Live-stream sensor data to a dashboard on the dev Mac. | Adds persistent connection overhead, requires async Python client code, and the use case (occasional analysis) does not need real-time. The data changes at 1 degF every ~10 minutes. | Use REST API polling at 1-5 minute intervals for any live monitoring need. Or just use the HA dashboard directly via browser. |
| **Re-home strategy (slam to floor + count up)** | If setpoint is totally lost, slam 25 presses to floor (80F) and count up. Guarantees known state. | Takes 25 * 500ms = 12.5 seconds minimum. If the display doesn't confirm floor, you're in worse shape. The probe+cache+direct-delta strategy already handles unknown setpoint by pressing down once and reading the display. Re-home is a sledgehammer for a problem already solved. The auto-refresh removal showed that unnecessary press sequences cause drift. | Keep probe+cache as the recovery mechanism. Only consider re-home if probe consistently fails (display decode broken). |

## Feature Dependencies

```
[Command-verify-retry (ESP32)]
    |---requires--> [Command result entity in HA]
    |---requires--> [Stability filtering (already done)]
    |---enhances--> [Setpoint drift detection (HA)]
    |---enhances--> [HA-side retry automation]

[Command result entity in HA]
    |---enhances--> [Command success rate dashboard]
    |---enhances--> [HA-side retry automation]

[Enphase power as heater ground truth]
    |---requires--> [Enphase Envoy integration (already available)]
    |---enhances--> [Thermal runaway protection (existing)]
    |---enhances--> [Thermal model accuracy]
    |---independent-of--> [Command-verify-retry]

[Time-series data export]
    |---requires--> [HA REST API access (already available)]
    |---enhances--> [Thermal model with outdoor correlation]
    |---independent-of--> [Command-verify-retry]

[Setpoint drift detection]
    |---requires--> [detected_setpoint sensor (already exists)]
    |---requires--> [Command result entity in HA]
```

### Dependency Notes

- **Command-verify-retry requires Command result entity:** The retry logic on the ESP32 side needs to surface its state (attempt count, final result) so HA automations can react.
- **Enphase power is independent of command path:** Power monitoring validates the heater binary sensor but does not interact with the button injection path. Can be built in parallel.
- **Time-series export is independent of everything:** It reads existing HA data. Can be built first as a foundation for validating all other features.
- **Setpoint drift detection conflicts with aggressive retry:** If the system detects drift and immediately retries, but the drift was intentional (user at tub), it fights the user. Need a "human override" detection window (e.g., suppress automation for 30 min after manual change).

## MVP Definition

### Launch With (Closed-Loop Trust v1)

The minimum set of features that lets TOU run unattended with confidence.

- [ ] **Command-verify with bounded retry on ESP32** -- Without retry, every TIMEOUT is a silent failure. This is the single most important feature for unattended operation.
- [ ] **Command result sensors exposed to HA** -- last_result, success_count, total_count as HA entities. Required for any HA-side logic.
- [ ] **HA-side retry automation** -- If ESP32 retry fails, HA tries once more after a delay. Two-layer defense.
- [ ] **Setpoint drift detection alert** -- Persistent notification if commanded vs detected setpoint diverge.

### Add After Validation (v1.x)

Features to add once command reliability is proven.

- [ ] **Enphase power as heater ground truth** -- Trigger: after 1 week of reliable command operation, add cross-validation. Independent of command path.
- [ ] **Time-series export script** -- Trigger: when you want to analyze command success rates and thermal model accuracy over time. Script replaces manual SCP+sqlite workflow.
- [ ] **Command success rate dashboard** -- Trigger: once you have 50+ command events to make the percentage meaningful.

### Future Consideration (v2+)

Features to defer until core trust is established.

- [ ] **Thermal model with outdoor temp correlation** -- Needs a full season of data to be meaningful. Defer until summer/fall 2026.
- [ ] **Published protocol documentation** -- Community value is high but not relevant to closed-loop trust.
- [ ] **Dual-source thermal runaway** -- Use Enphase power AND display heater binary for redundant runaway detection. Defer until power monitoring is validated.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Command-verify bounded retry (ESP32) | HIGH | MEDIUM | P1 |
| Command result sensors to HA | HIGH | LOW | P1 |
| HA-side retry automation | HIGH | LOW | P1 |
| Setpoint drift detection | HIGH | LOW | P1 |
| Enphase power ground truth | MEDIUM | MEDIUM | P2 |
| Time-series export script | MEDIUM | LOW | P2 |
| Command success rate dashboard | LOW | LOW | P2 |
| Thermal model outdoor correlation | LOW | LOW | P3 |
| Dual-source thermal runaway | MEDIUM | MEDIUM | P3 |

**Priority key:**
- P1: Must have for closed-loop trust milestone
- P2: Should have, add when command path is stable
- P3: Nice to have, future consideration

## Domain-Specific Research Findings

### 1. Command-Verify-Retry Patterns (Industrial Control)

**Confidence: MEDIUM** (patterns synthesized from multiple sources; no single canonical "command-verify-retry" reference exists as a named pattern)

The pattern is well-established in practice but unnamed in literature. Industrial SCADA/PLC systems implement it as:

1. **COMMAND** -- Send actuator signal
2. **VERIFY** -- Read sensor/feedback to confirm state change
3. **RETRY** -- If mismatch, retry with bounded count and increasing delay
4. **SAFE STATE** -- After max retries, enter known-safe configuration

**Key principles from established practice:**
- **Bounded retries with backoff:** Never retry infinitely. Use 2-3 attempts with exponential delay (e.g., 5s, 15s, 60s). Jitter is useful in distributed systems but irrelevant here (single actuator).
- **Classify errors:** Transient (lost press, display in transition) vs permanent (wiring broken, controller in error mode). Only retry transient failures.
- **Guard conditions on retry:** Track attempt count in state. Transition to ERROR state when max reached, not back to COMMAND.
- **Timeout-based safety:** The existing `verify_timeout_ms: 10000` is the right approach. A wireless sensor/actuator network paper uses 3s as timeout before entering safety control state -- 10s is reasonable for a slow physical system.
- **Last-known-good fallback:** The existing `known_setpoint_ = NAN` on failure (forcing probe on next attempt) is correct -- it's the embedded equivalent of "don't cache stale state."

**Specific recommendation for Tubtron:**
Add a `RETRYING` phase to `InjectorPhase` enum. After VERIFY timeout, if `retry_count_ < max_retries_` (default 2), transition to RETRYING (delay), then back to PROBING (invalidate cache, start fresh). After max retries, transition to COOLDOWN with `InjectorResult::FAILED` (new result type). Surface `retry_count_` as a sensor.

### 2. Time-Series Data Export from Home Assistant

**Confidence: HIGH** (official HA REST API documentation verified)

Three viable approaches, ordered by recommendation:

**Option A (Recommended): REST API from dev machine**
- Endpoint: `GET /api/history/period/{start}?filter_entity_id={ids}&end_time={end}&minimal_response&no_attributes`
- Auth: Long-lived access token in `Authorization: Bearer TOKEN` header
- Performance: `minimal_response` + `no_attributes` flags make it "much faster" per official docs
- Implementation: Python `requests` library, ~30 lines of code
- Zero load on HA beyond the query itself. No infrastructure to maintain.

**Option B: SCP + SQLite (already working)**
- The `analyze_heating.py` script already does this: `scp homeassistant@homeassistant.local:/config/home-assistant_v2.db ./ha.db`
- Pro: Full DB access, can run arbitrary SQL
- Con: Copies entire DB (can be large), locks during copy, requires SSH access configured

**Option C: InfluxDB (not recommended)**
- Requires add-on installation, ongoing maintenance, RAM on RPi4
- Runs parallel to HA DB, not a replacement
- Only justified if you need Grafana dashboards or >1 year of high-frequency data

**Recommendation:** Use REST API (Option A) for targeted entity history pulls. Keep SCP+SQLite (Option B) for deep analysis. Do not add InfluxDB.

### 3. Power Monitoring for Heater State Detection

**Confidence: HIGH** (Enphase integration and API endpoints well-documented)

**The 4kW heater is an ideal detection target:**
- Resistive load = clean, flat power signature (no motor inrush, no variable speed)
- 4000W step is large enough to detect against whole-home baseline
- Duty cycles on/off to maintain temperature, creating obvious square-wave pattern

**Enphase data path:**
1. Enphase Envoy core integration in HA (auto-discovered on same network)
2. Exposes `sensor.envoy_current_power_consumption` (or similar, depends on CT config)
3. Local API endpoint `/ivp/meters/readings` returns `activePower` in ~64ms
4. Default polling: 60s (configurable to 5s minimum via HACS custom integration)

**Detection approach:**
- Simple threshold: `consumption_watts > baseline + 3500` = heater likely on
- Better: Track rolling 5-min average of power. A 4kW step is unambiguous.
- Cross-reference: Compare HA power-derived heater state vs `binary_sensor.tublemetry_hot_tub_heater` (display-decoded). Agreement = high confidence. Sustained disagreement = alert.

**Known limitation:** If another large 240V appliance (electric dryer, EV charger, heat pump) runs simultaneously, the threshold may false-trigger. Mitigation: use the *change* in power (delta), not absolute level. Heater cycles produce characteristic 4kW steps; other loads have different signatures.

### 4. Embedded Safety for Home Automation

**Confidence: MEDIUM-HIGH** (IEC 61508 principles well-documented; application to hobby systems is synthesized from general safety engineering)

**Applicable IEC 61508 principles (without formal compliance):**

1. **Hazard identification:** What can go wrong?
   - Heater stuck on -> water overtemp -> burn risk, equipment damage
   - Setpoint set wrong -> energy waste, tub not ready
   - ESP32 crash -> no control -> tub defaults to Balboa's own thermostat (inherently safe)
   - WiFi loss -> HA can't command -> tub holds last Balboa setpoint (inherently safe)

2. **Safe state definition:**
   - For this system: the *safest* state is "do nothing." The Balboa VS300FL4 has its own thermostat. If the ESP32 and all automation stops, the tub regulates to whatever setpoint was last physically set. This is NOT dangerous.
   - The only dangerous state is the ESP32 *actively* driving the setpoint wrong (e.g., stuck in a loop pressing temp-up). Bounded retry and max-press limits prevent this.

3. **Defense in depth (already implemented):**
   - Layer 1: Balboa's own thermostat (hardware, independent of ESP32)
   - Layer 2: ESP32 `TEMP_CEILING = 104.0f` and `TEMP_FLOOR = 80.0f` (software clamp)
   - Layer 3: HA thermal runaway automation (temp > setpoint + 2F for 5min -> drop to 80F)
   - Layer 4 (proposed): Enphase power cross-validation (heater on when it shouldn't be)

4. **Watchdog and recovery:**
   - ESPHome safe_mode (10 consecutive boot failures -> OTA-only mode)
   - WiFi reboot_timeout (10min disconnect -> reboot)
   - API reboot_timeout (15min no HA connection -> reboot)
   - These are equivalent to task-level watchdog + graceful degradation

5. **Fail-functional, not fail-safe:**
   - A true fail-safe would cut power to the heater. Not needed here because Balboa's thermostat is the ultimate safety layer.
   - The system fails *functional* -- if automation dies, manual control still works.

**Key insight:** The biggest safety risk in this system is not hardware failure -- it's *software actively doing the wrong thing* (pressing buttons in a loop, setting wrong setpoint). The primary safety feature is therefore **bounded behavior**: max retries, max presses, timeout-based abort, and conservative defaults.

### 5. Signal Processing for Noisy Digital Signals

**Confidence: HIGH** (ESPHome filters well-documented; ESP32 GPIO behavior confirmed by Espressif)

**Current approach is already correct for this system:**

The display decode pipeline processes at 60Hz via ISR, decodes 7-segment frames, and applies a stability filter (3 consecutive identical frames required before publishing). This is the right architecture.

**Where to apply filtering:**

| Signal | Current Filtering | Recommendation |
|--------|------------------|----------------|
| Temperature (from display decode) | Stability filter (3 frames) + ESPHome `heartbeat: 30s` + `delta: 1.0` | Sufficient. Add `median` filter (window 5) in ESPHome YAML if spurious values seen. |
| Heater binary sensor | None visible | Add ESPHome `delayed_on: 2s` / `delayed_off: 5s` to avoid rapid toggling from display decode noise. |
| Enphase power (future) | N/A | ESPHome `sliding_window_moving_average` (window 5, send_every 5) on the power sensor. Smooths 1s power jitter. |
| Decode confidence | None visible | Add ESPHome `exponential_moving_average` (alpha 0.1, send_every 15) to smooth confidence metric. |

**ESP32-side vs Python-side processing:**
- **ESP32-side:** Debouncing, stability filtering, hysteresis (threshold + dead band). These prevent bad data from entering HA at all. Low CPU cost, high value.
- **Python-side:** Trend analysis, rate computation, correlation with outdoor temp. These need historical data and benefit from pandas/numpy. Run on dev Mac, not ESP32.
- **HA-side (template sensors):** Rolling averages, ETA computation, cross-sensor comparison. HA's Jinja2 templates handle this well for real-time dashboard values.

**Specific ESPHome filter recommendations:**
```yaml
# Temperature: already good, optionally add median for spike rejection
filters:
  - median:
      window_size: 5
      send_every: 1
  - heartbeat: 30s
  - delta: 1.0

# Heater binary: debounce rapid on/off
filters:
  - delayed_on: 2s
  - delayed_off: 5s
```

The `delayed_on` / `delayed_off` pattern is the binary equivalent of hysteresis -- it prevents rapid state transitions from noisy decode. A 2s on-delay means a brief flash of the heater indicator doesn't register as "heater on," and a 5s off-delay means a brief dropout doesn't register as "heater off." The asymmetry is intentional: you care more about false "heater off" (masks thermal runaway) than false "heater on."

## Sources

### Official Documentation
- [Home Assistant REST API](https://developers.home-assistant.io/docs/api/rest/) -- history endpoints, minimal_response, no_attributes flags
- [Home Assistant WebSocket API](https://developers.home-assistant.io/docs/api/websocket/) -- event subscription pattern
- [Enphase Envoy Integration](https://www.home-assistant.io/integrations/enphase_envoy/) -- core HA integration for Enphase
- [Enphase IQ Gateway Local API](https://enphase.com/download/iq-gateway-local-apis-or-ui-access-using-token) -- local API endpoints, token auth
- [ESPHome Sensor Component](https://esphome.io/components/sensor/) -- all filter types and parameters
- [ESP-IDF Capacitive Touch Docs](https://docs.espressif.com/projects/esp-idf/en/latest/esp32p4/api-reference/peripherals/cap_touch_sens.html) -- hysteresis + debounce pattern from Espressif

### Industrial Control / Safety
- [IEC 61508 Overview](https://assets.iec.ch/public/acos/IEC%2061508%20&%20Functional%20Safety-2022.pdf) -- functional safety lifecycle
- [LDRA IEC 61508 Guide](https://ldra.com/iec-61508/) -- software safety techniques (defensive programming, modular design, fault detection)
- [Avench: IEC 61508 for Embedded Systems](https://avench.com/iot/why-iec-61508-is-the-gold-standard-for-functional-safety-in-embedded-systems/) -- SIL levels, safety lifecycle
- [Inspiro: Fail-Safe Systems for Embedded](https://www.inspiro.nl/en/how-to-design-fail-safe-systems-for-critical-embedded-applications/) -- watchdog design, error detection, defensive programming
- [In Compliance: Robust Watchdog Timers](https://incompliancemag.com/implementing-robust-watchdog-timers-for-embedded-systems/) -- task-level monitoring, windowed watchdogs
- [Beningo: Watchdog Timer in Every Embedded Device](https://www.beningo.com/a-watchdog-timer-is-needed-in-every-embedded-device/) -- startup diagnostics, safe-mode startup

### Retry Patterns
- [CNStra: Error Handling in State Machines](https://cnstra.org/docs/recipes/error-handling/) -- bounded retries with exponential backoff, context tracking
- [Archimetric: State Machine Diagrams for IoT](https://www.archimetric.com/state-machine-diagram-iot-developers/) -- request-response pattern with ACK/NACK/retry
- [Archimetric: State Machine Checklist](https://www.archimetric.com/state-machine-diagram-checklist-embedded-systems/) -- retry limits, guard conditions

### Power Monitoring
- [Enphase-API Unofficial Documentation](https://github.com/Matthew1471/Enphase-API) -- comprehensive local API endpoint catalog
- [Whirlpool: Enphase Local API Performance](https://forums.whirlpool.net.au/archive/3xv60w6y) -- `/ivp/meters/readings` 64ms response time

### Data Export
- [homeassistant-statistics (CSV/TSV export)](https://github.com/klausj1/homeassistant-statistics) -- long-term statistics export integration
- [SmartHomeScene: HA Database Model](https://smarthomescene.com/blog/understanding-home-assistants-database-and-statistics-model/) -- states vs statistics table structure
- [homeassistant-api Python Library](https://homeassistantapi.readthedocs.io/en/latest/api.html) -- Python client for HA REST API

### ESP32 Signal Processing
- [ESP_DSP: Real-Time DSP on ESP32](https://github.com/bobh/ESP_DSP) -- DSP library for ESP32
- [ESP32 GPIO Spurious Interrupts](https://github.com/espressif/arduino-esp32/issues/4172) -- slow edge / noisy signal issue documentation

---
*Feature research for: Closed-loop embedded hot tub control*
*Researched: 2026-04-12*
