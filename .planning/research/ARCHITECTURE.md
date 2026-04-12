# Architecture Patterns

**Domain:** Closed-loop embedded control + Home Assistant integration
**Researched:** 2026-04-12

## Current Architecture (As-Is)

```
+------------------------------------------------------------------+
|                          Home Assistant (RPi4)                     |
|                                                                    |
|  [TOU Automation]     [Thermal Runaway]     [Heating Tracker]     |
|       |                     |                     |                |
|       v                     v                     v                |
|  number.set_value      system_log.write    input_number.set_value |
|       |                     |                     |                |
|       +----> ESPHome Native API <----+             |                |
|              (persistent TCP)        |             |                |
|                    |                 |             |                |
|  [SQL Sensors] -- SQLite DB    [Template Sensors]                  |
|  (heating/cooling rates)       (preheat ETA, outdoor temp)         |
+------------------------------------------------------------------+
                    |
                    | ESPHome Native API (protobuf over TCP)
                    |
+------------------------------------------------------------------+
|                   ESP32 (ESPHome firmware)                         |
|                                                                    |
|  [ISR: clock_isr_]  --> FrameData (volatile)                      |
|       |                                                            |
|  [TublemetryDisplay::loop()]                                       |
|       |                                                            |
|       +--> process_frame_() --> decode_7seg_()                     |
|       |         |                                                  |
|       |         +--> classify_display_state_()                     |
|       |         |         |                                        |
|       |         |         +--> publish temperature sensor          |
|       |         |         +--> publish setpoint (set-mode detect)  |
|       |         |         +--> feed_display_temperature() to       |
|       |         |              ButtonInjector                      |
|       |         |                                                  |
|       |         +--> publish heater/pump/light binary sensors      |
|       |                                                            |
|  [ButtonInjector::loop()]  <-- state machine                       |
|       |  Phases: IDLE -> PROBING -> ADJUSTING -> VERIFYING ->     |
|       |          COOLDOWN                                          |
|       |                                                            |
|  [TublemetrySetpoint::control()] <-- number entity from HA        |
|       +--> injector->request_temperature()                         |
+------------------------------------------------------------------+
                    |
                    | GPIO (photorelays + clock/data)
                    |
+------------------------------------------------------------------+
|                   Balboa VS300FL4 Controller                       |
|  [Display bus: 24-bit sync clock+data @ 60Hz]                     |
|  [Button lines: analog, bridged by AQY212EH photorelays]          |
+------------------------------------------------------------------+
```

## Recommended Architecture (To-Be)

### Question 1: Where Does Retry Logic Live?

**Answer: Primarily in the C++ ButtonInjector, with HA as escalation layer.**

The retry loop belongs in firmware because:

1. **Timing sensitivity.** The ButtonInjector already operates a non-blocking state machine (PROBING -> ADJUSTING -> VERIFYING -> COOLDOWN) with sub-second timing. Retry needs the same tight coupling to the display decode pipeline -- `feed_display_temperature()` is called every frame (~60Hz). HA automations poll at 1-second minimum granularity and add network round-trip latency.

2. **State ownership.** The ButtonInjector owns `known_setpoint_`, `last_display_temp_`, `probed_setpoint_`, and all the phase transitions. Having HA re-issue commands after timeout means HA would need to understand whether the injector is mid-sequence, which violates encapsulation.

3. **Memory/compute is fine.** Retry is a counter + state transition, not a memory-intensive operation. The ESP32-WROOM-32 has ~160KB usable DRAM; the current component uses negligible RAM (a few hundred bytes of state). Adding a retry counter and attempt tracking adds maybe 20 bytes.

**Specific firmware changes:**

```
ButtonInjector additions:
  - uint8_t retry_count_{0}
  - uint8_t max_retries_{2}        // configurable from YAML
  - InjectorResult -> add RETRY_EXHAUSTED
  - finish_sequence_(): on TIMEOUT, if retry_count_ < max_retries_,
    re-enter PROBING (setpoint now unknown), increment retry_count_
  - On SUCCESS or RETRY_EXHAUSTED, reset retry_count_ to 0
```

**HA's role is escalation, not retry:**

```
HA automation (new):
  trigger: esphome.setpoint_command_result event
  condition: result == "retry_exhausted" or result == "timeout"
  action:
    - persistent_notification.create (alert user)
    - Optionally: wait 5 min, re-send the same number.set_value
```

The ESP32 fires a `homeassistant.event` (via `CustomAPIDevice::fire_homeassistant_event()`) after each completed sequence with structured data: `{result: "success"|"timeout"|"retry_exhausted", target: 104, attempts: 3}`. This requires:
- Adding `api: homeassistant_services: true` to the YAML (already effectively true since HA actions are used)
- Having ButtonInjector inherit from or access a `CustomAPIDevice` instance to fire events
- Alternative (simpler): expose result as a text_sensor that HA triggers on

**Recommended simpler approach:** Expose `last_result` and `last_target` as ESPHome sensors (text_sensor for result, sensor for target). HA automations trigger on state change of the result sensor. No need for `CustomAPIDevice` inheritance -- just add two more sensor publications in `finish_sequence_()`. This avoids any C++ API dependency changes.

```
New sensors in tublemetry.yaml:
  text_sensor:
    - platform: tublemetry_display
      injection_result:
        name: "Hot Tub Injection Result"   # "success" | "timeout" | "retry_exhausted"
      injection_target:
        name: "Hot Tub Injection Target"   # "104" etc.
  sensor:
    - platform: tublemetry_display
      injection_attempts:
        name: "Hot Tub Injection Attempts"  # numeric counter
```

### Question 2: Data Pipeline -- Getting History to Mac for Analysis

**Answer: Pull via HA REST API for short-term; SCP the SQLite DB for deep analysis.**

Three options evaluated:

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| **HA REST API `/api/history/period`** | No DB access needed, works over network, supports `filter_entity_id` and `minimal_response` | Limited to recorder retention (default 10 days), no long-term statistics, JSON not CSV | Good for recent operational checks |
| **SCP the SQLite DB** | Full history, supports the existing `analyze_heating.py` script, SQL flexibility | Requires SSH/SCP access to RPi, DB may be locked during write | Best for deep analysis |
| **Push to external DB (InfluxDB/TimescaleDB)** | Always-on time-series, Grafana integration, no SCP needed | New infrastructure to maintain, RPi4 may not have resources for another DB, complexity | Overkill for single-user system |

**Recommendation: Two-tier approach.**

**Tier 1 -- Automated daily export (new):**
A Python script on the Mac that pulls recent data via the HA REST API:

```python
# scripts/pull_ha_history.py
# Uses: requests, pandas
# Auth: Long-lived access token
# Pulls: last N days of entity history via /api/history/period
# Outputs: CSV per entity or single merged DataFrame
```

This replaces the need to SCP the DB for routine checks. The REST API returns JSON arrays of state changes; the script converts to CSV. Limited to recorder retention window (configure HA to keep 30 days for hot tub entities).

**Tier 2 -- SCP for deep analysis (existing pattern, improved):**

```bash
# Already documented in analyze_heating.py:
scp homeassistant@homeassistant.local:/config/home-assistant_v2.db ./ha.db
uv run scripts/analyze_heating.py --db ./ha.db --csv out.csv --plot
```

Enhance `analyze_heating.py` to also accept REST API JSON as input (alternative to SQLite), so the same analysis code works with both data sources.

**Why NOT InfluxDB:** The user runs HA OS on an RPi4 with an SD card. InfluxDB's write amplification would shorten SD card life and consume resources the Pi can't spare. The hot tub generates ~10 state changes per minute across all entities -- trivial for SQLite, but InfluxDB on RPi4 is a known pain point in the HA community.

**Long-term statistics note:** HA's WebSocket API supports `recorder/statistics_during_period` for long-term hourly aggregates. If needed later, a script can use `websockets` + `homeassistant-api` Python packages to pull these. Not needed for MVP.

### Question 3: Enphase Power Correlation with Heater State

**Answer: Template binary sensor in HA comparing whole-home power against a threshold.**

The hot tub has a 4kW heater on 240V. When it turns on, whole-home consumption jumps by ~4000W. The Enphase Envoy integration exposes `sensor.envoy_SERIAL_current_power_consumption` (whole-home watts, real-time). The approach:

**Step 1: Create a power-derived heater binary sensor:**

```yaml
# ha/templates.yaml (add to existing)
- binary_sensor:
    - name: "Hot Tub Heater (Power)"
      device_class: power
      # True when whole-home consumption exceeds baseline by heater-sized amount
      state: >
        {% set power = states('sensor.envoy_SERIAL_current_power_consumption') | float(0) %}
        {% set baseline = states('input_number.home_baseline_watts') | float(500) %}
        {{ power > baseline + 3000 }}
      delay_on:
        seconds: 30
      delay_off:
        seconds: 30
```

The `delay_on`/`delay_off` filters prevent flicker from brief power spikes (microwave, HVAC). The 30-second window is appropriate because the hot tub heater runs in sustained 10-60 minute cycles.

**Step 2: Cross-validate with display-decoded heater state:**

```yaml
# ha/templates.yaml (add to existing)
- binary_sensor:
    - name: "Hot Tub Heater Mismatch"
      # True = the two heater signals disagree for > 2 minutes
      state: >
        {% set display_heater = is_state('binary_sensor.tublemetry_hot_tub_heater', 'on') %}
        {% set power_heater = is_state('binary_sensor.hot_tub_heater_power', 'on') %}
        {{ display_heater != power_heater }}
      delay_on:
        minutes: 2
```

**Why template sensor, not automation:**

- Template sensors are continuously evaluated and produce a time series in the recorder. This means the power-derived heater state is available for historical analysis alongside the display-decoded heater state.
- An automation would fire once and log once, losing the continuous correlation data.
- Template sensors compose: the mismatch sensor references the power sensor, which references the Envoy sensor. Clean dependency chain.

**Baseline calibration:** The `input_number.home_baseline_watts` helper stores the typical non-tub household load. Start at 500W, refine from data. A future enhancement could auto-calibrate by observing the delta when the display-decoded heater turns on/off.

**Entity ID mapping needed:** The user needs to identify their actual Enphase sensor entity ID. It follows the pattern `sensor.envoy_SERIAL_current_power_consumption` where SERIAL is the Envoy gateway's serial number. Check HA Developer Tools > States and search for "envoy".

### Question 4: Sensor Fusion / Cross-Validation -- Firmware or HA?

**Answer: HA, not firmware.**

Sensor fusion for this system means comparing independent signals to detect faults:
- Display-decoded heater state vs. power-derived heater state
- Display-decoded temperature vs. expected temperature given heater runtime
- Setpoint command result vs. actual displayed setpoint after timeout

**All of this belongs in HA because:**

1. **The ESP32 doesn't have the Enphase data.** Power monitoring comes from a completely separate network device (Enphase Envoy via its own integration). The ESP32 would need to subscribe to HA entities via the native API to get this data, which adds fragile coupling and uses API bandwidth.

2. **Template sensors are the right abstraction.** HA's template engine is built for exactly this -- combining state from multiple devices into derived sensors. The mismatch detector (Q3 above) is a clean example.

3. **Recorder provides the audit trail.** When sensors disagree, you want the history. HA's recorder stores every state change for template sensors automatically. On the ESP32, you'd need to implement logging, which is limited to serial output or the ESPHome logger (no persistent storage).

4. **Firmware should be dumb and reliable.** The ESP32's job is: decode display frames, inject button presses, report raw state. It should not make policy decisions based on cross-device sensor data. Keep the firmware's responsibility surface small.

**What DOES belong in firmware:**
- The retry logic (Q1) -- because it's internal to the button injection state machine
- Watchdog / sanity checks on the display decode pipeline (e.g., "no frames received for 60s = mark sensor unavailable")
- Safety floor/ceiling clamping on `request_temperature()` (already implemented: 80-104F range)

**New HA template sensors for cross-validation:**

| Sensor | Inputs | Purpose |
|--------|--------|---------|
| `binary_sensor.hot_tub_heater_power` | Enphase consumption sensor | Independent heater state from power |
| `binary_sensor.hot_tub_heater_mismatch` | Display heater + power heater | Fault detection |
| `sensor.hot_tub_heater_agreement_pct` | Both heater signals over time | Confidence metric |
| `binary_sensor.hot_tub_display_stale` | `last_update` sensor age | ESP32 communication health |

### Question 5: ESP32 vs. HA Responsibility Boundary

**Answer: ESP32 owns real-time hardware interaction. HA owns policy, correlation, and persistence.**

```
+---------------------------+----------------------------------+
|     ESP32 Responsibility   |     HA Responsibility            |
+---------------------------+----------------------------------+
| ISR-driven frame decode   | TOU schedule (when to heat)      |
| 7-segment lookup          | Retry escalation (after firmware  |
| Stability filtering       |   retries exhausted)             |
| Set-mode detection        | Thermal runaway protection       |
| Button press timing       | Power-based heater validation    |
| Press-verify-retry loop   | Sensor fusion / cross-validation |
| Setpoint caching          | Data persistence (recorder)      |
| Safety clamping (80-104F) | Data export (REST API / scripts) |
| Heater/pump/light status  | Dashboard visualization          |
|   bit extraction          | Notification / alerting          |
| Publish raw state to HA   | Thermal model (heating/cooling   |
|                           |   rate computation via SQL)      |
+---------------------------+----------------------------------+
```

**The boundary principle:** If it needs sub-second timing or direct GPIO access, it's firmware. If it needs data from multiple devices, persistent storage, or user-facing policy, it's HA.

**MQTT is NOT needed.** The ESPHome native API provides everything required:
- Bidirectional: HA sends `number.set_value`, ESP32 publishes sensor states
- Real-time: persistent TCP connection, push-based updates, no polling
- Structured: sensor/number/binary_sensor/text_sensor entities are first-class
- Events: `homeassistant.event` or sensor state changes for command results

MQTT would only be needed if: (a) you wanted non-HA consumers of the data stream, (b) you needed store-and-forward during HA downtime, or (c) you were integrating with a third-party system. None of these apply.

## Component Boundaries (New + Modified)

| Component | Location | Status | Responsibility |
|-----------|----------|--------|----------------|
| `tublemetry_display.cpp` | ESP32 | **Existing** | Frame decode, state classification, sensor publish |
| `button_injector.cpp` | ESP32 | **Modify** | Add retry loop, expose result/attempt sensors |
| `tublemetry_setpoint.cpp` | ESP32 | **Existing** | Number entity, delegates to injector |
| `tou_automation.yaml` | HA | **Existing** | TOU schedule, setpoint commands |
| `thermal_runaway.yaml` | HA | **Existing** | Safety: overshoot detection |
| `sensors.yaml` | HA | **Existing** | SQL sensors for thermal model |
| `templates.yaml` | HA | **Modify** | Add power-derived heater, mismatch, stale detector |
| `command_monitor.yaml` | HA | **New** | React to injection result sensors (escalation) |
| `pull_ha_history.py` | Mac | **New** | REST API data export script |
| `analyze_heating.py` | Mac | **Modify** | Accept REST API JSON input alongside SQLite |

## Data Flow (New Capabilities)

### Command-Verify-Retry Flow

```
HA TOU automation
  |
  v
number.set_value(104)
  |
  v (ESPHome native API)
TublemetrySetpoint::control(104)
  |
  v
ButtonInjector::request_temperature(104)
  |
  v
[PROBING] -> display shows current SP
  |
  v
[ADJUSTING] -> N presses up/down
  |
  v
[VERIFYING] -> wait for display == 104
  |                    |
  | (match)            | (timeout, retries < max)
  v                    v
[SUCCESS]         [retry: re-enter PROBING]
  |                    |
  | publish            | (timeout, retries >= max)
  | text_sensor:       v
  | "success"     [RETRY_EXHAUSTED]
  |                    |
  v                    | publish text_sensor: "retry_exhausted"
[COOLDOWN]             v
                  [COOLDOWN]
                       |
                       v (HA sees text_sensor change)
                  command_monitor.yaml fires
                       |
                       v
                  persistent_notification + optional re-attempt
```

### Power Correlation Flow

```
Enphase Envoy (network device)
  |
  v (Enphase integration, native polling)
sensor.envoy_SERIAL_current_power_consumption  (watts)
  |
  v (HA template sensor)
binary_sensor.hot_tub_heater_power  (on if watts > baseline + 3000)
  |
  +------+
  |      |
  v      v
  |  binary_sensor.tublemetry_hot_tub_heater  (from display decode)
  |      |
  v      v
binary_sensor.hot_tub_heater_mismatch  (disagree > 2 min)
  |
  v (if mismatch persists)
automation: alert + log
```

### Data Export Flow

```
Tier 1 (routine):
  Mac                           RPi4 (HA)
  pull_ha_history.py  -------> /api/history/period
       |              <------- JSON response
       v
  pandas DataFrame -> CSV -> analyze_heating.py

Tier 2 (deep analysis):
  Mac                           RPi4 (HA)
  scp                 -------> /config/home-assistant_v2.db
       |              <------- SQLite file
       v
  analyze_heating.py --db ./ha.db --csv --plot
```

## Patterns to Follow

### Pattern 1: Firmware State Machine with HA Observation

**What:** Keep complex real-time logic in firmware as a non-blocking state machine. Expose phase, result, and diagnostic data as ESPHome sensors. HA observes and reacts to state changes.

**When:** Any hardware interaction requiring tight timing (button presses, display decode, relay control).

**Why:** Decouples real-time control from network-dependent policy. The ESP32 works correctly even if HA is temporarily unreachable (API reboot_timeout handles extended disconnection).

### Pattern 2: Template Sensor Composition for Cross-Device Logic

**What:** Derive higher-order state from multiple device sensors using HA template sensors. Chain template sensors for layered logic.

**When:** Combining data from ESP32 display decode + Enphase power monitoring + weather data.

**Example:**
```yaml
# Layer 1: raw device data (existing)
binary_sensor.tublemetry_hot_tub_heater     # from ESP32
sensor.envoy_SERIAL_current_power_consumption  # from Enphase

# Layer 2: derived state (new)
binary_sensor.hot_tub_heater_power          # threshold on power

# Layer 3: cross-validation (new)
binary_sensor.hot_tub_heater_mismatch       # compare layers

# Layer 4: policy (existing pattern)
automation: thermal_runaway  # act on layer 3
```

### Pattern 3: Publish-on-Change with Diagnostic Counters

**What:** Only publish sensor state when it actually changes (avoid database bloat), but expose cumulative counters for diagnostics.

**When:** High-frequency internal state (60Hz frame decode) that would overwhelm HA's recorder if published every tick.

**Already implemented for:** display_string, raw_hex, heater/pump/light binary sensors.

**Extend to:** injection result, injection attempts counter, retry count.

## Anti-Patterns to Avoid

### Anti-Pattern 1: HA Automation as Retry Loop

**What:** Using HA automations with `delay` + `repeat` to retry setpoint commands.

**Why bad:** HA automation delays are not precise (1-second granularity minimum). The delay between "send command" and "check result" introduces a network round-trip where the display state could change. The ButtonInjector already has sub-100ms timing; HA cannot match this.

**Instead:** Firmware retry (Q1 above). HA only handles escalation after firmware retries are exhausted.

### Anti-Pattern 2: Polling ESP32 for Enphase Data

**What:** Having the ESP32 subscribe to HA entities (via `homeassistant` sensor platform) to get Enphase power data, then doing cross-validation in firmware.

**Why bad:** Adds ~500ms latency per state update over the API. Consumes API bandwidth. Makes the ESP32 dependent on HA being available for safety logic. Increases firmware complexity for logic that HA template sensors handle natively.

**Instead:** All cross-device logic in HA template sensors. ESP32 publishes raw state only.

### Anti-Pattern 3: External Time-Series Database on RPi4

**What:** Running InfluxDB or TimescaleDB on the RPi4 alongside HA for historical analysis.

**Why bad:** RPi4 on SD card has limited I/O. InfluxDB's write amplification degrades SD card life. Added maintenance burden for a single-user system with ~10 state changes/minute. The existing SQLite recorder + SCP workflow already works.

**Instead:** Pull data via REST API (Tier 1) or SCP the SQLite DB (Tier 2). Run analysis on the Mac where resources are abundant.

## Scalability Considerations

Not applicable in the traditional sense (single hot tub, single user), but relevant for **data volume and system health:**

| Concern | Current | With New Features |
|---------|---------|-------------------|
| ESP32 RAM | ~54KB used / 320KB total (16.6%) | +20 bytes for retry state, negligible |
| ESP32 Flash | Near limit with many ESPHome components | Monitor; retry adds <1KB code |
| HA recorder DB size | Grows with state changes | Power sensor adds ~1 change/min; manageable |
| Network traffic | Native API: minimal, push-based | No increase (sensors publish on change) |
| SD card wear (RPi4) | Normal HA recorder writes | No additional writes beyond new template sensors |

## Build Order (Dependency-Aware)

Based on the architecture above, the recommended build order:

1. **Firmware retry loop** -- Modify `button_injector.cpp` to add retry counter and expose result/attempt sensors. This is the foundation that everything else observes. No HA changes needed for this to work (sensors just appear).

2. **Command result monitoring** -- New HA automation (`command_monitor.yaml`) that triggers on the injection result sensor. Depends on (1) being deployed.

3. **Power-derived heater sensor** -- New template sensors in HA. Independent of (1) and (2); requires only identifying the Enphase entity ID. Can be built in parallel with (1).

4. **Heater mismatch / cross-validation** -- Template sensors comparing display heater and power heater. Depends on (3).

5. **Data export script** -- Python script on Mac. Independent of all firmware changes. Can be built in parallel with everything.

6. **Enhanced analysis** -- Update `analyze_heating.py` to consume REST API data. Depends on (5).

**Parallelizable:** (1) and (3) and (5) can all proceed simultaneously. (2) depends on (1). (4) depends on (3). (6) depends on (5).

## Sources

- [ESPHome Native API Component](https://esphome.io/components/api/)
- [ESPHome CustomAPIDevice Reference](https://esphome.io/api/classesphome_1_1api_1_1_custom_a_p_i_device.html)
- [ESPHome 2025.12.0 Changelog (action responses)](https://esphome.io/changelog/2025.12.0/)
- [Home Assistant REST API Developer Docs](https://developers.home-assistant.io/docs/api/rest/)
- [Enphase Envoy Integration](https://www.home-assistant.io/integrations/enphase_envoy/)
- [HA Community: Appliance Power Monitor Blueprint](https://community.home-assistant.io/t/detect-and-monitor-the-state-of-an-appliance-based-on-its-power-consumption-v2-1-1-updated/421670)
- [HA Community: Long Term Statistics via WebSocket API](https://community.home-assistant.io/t/can-i-get-long-term-statistics-from-the-rest-api/761444)
- [ESP32 Memory Types (ESP-IDF docs)](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/memory-types.html)
- [ESPHome 2025.11.0 Memory Optimizations](https://esphome.io/changelog/2025.11.0/)
