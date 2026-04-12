# Technology Stack

**Project:** Tubtron v2.0 -- Closed-Loop Trust
**Researched:** 2026-04-12
**Scope:** Stack ADDITIONS for new milestone features only. Existing ESP32/ESPHome/HA stack is validated and not re-researched.

## Recommended Stack Additions

### 1. Command Reliability (Firmware-Side)

The existing `ButtonInjector` state machine (PROBE -> ADJUST -> VERIFY -> COOLDOWN) already handles single-attempt command-verify. What is missing is **retry on verification failure** and **surfacing success/failure to HA**.

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| ESPHome `set_timeout` + manual backoff | ESPHome >=2026.2.0 | Command retry with exponential backoff | `set_retry`/`RetryResult` was deprecated in ESPHome 2026.2.0, removed in 2026.8.0. The replacement is chained `set_timeout` calls with a member variable tracking attempts and interval. Since tublemetry already uses a hand-rolled state machine, the cleanest approach is to add retry logic directly into `ButtonInjector::finish_sequence_()` rather than using ESPHome scheduling primitives. |
| ESPHome `text_sensor` | Already present | Surface injection result (success/timeout/retry count) to HA | The `injection_state_sensor_` already exists but only publishes phase. Extend to publish result + attempt count so HA automations can detect persistent failures. |
| ESPHome sensor filters: `delta`, `heartbeat` | Already present | Noise rejection on display temperature reads | Already in use. No new filters needed firmware-side. |

**What NOT to add (firmware-side):**

| Rejected | Why |
|----------|-----|
| Kalman filter on ESP32 | Overkill. The temperature signal is a 3-digit integer from a 7-segment display decoded via GPIO interrupts -- it is inherently quantized to 1F resolution with no analog noise. The existing stability filter (3 consecutive identical frames) is the correct approach. Kalman filtering is for continuous noisy analog signals (IMU, ADC), not decoded digital displays. Adding it wastes ~2-8KB heap on a device with ~100-150KB free. |
| esp-dsp library | Not needed. No DSP operations required -- no FFT, no matrix math, no signal filtering. The display protocol is synchronous clock+data, not an analog signal. |
| TinyEKF | Same reasoning as Kalman. The "sensor" here is a decoded digital display, not a noisy analog measurement. |
| MISRA-style static analysis tooling | Disproportionate for a single-installation home project. The MISRA-inspired principles (defensive coding, bounds checking, safe state on failure) should be applied as coding discipline, not enforced by tooling. The ESP32 controls photorelays that simulate button presses -- it cannot directly drive the 4kW heater. The Balboa controller's own thermostat is the safety-critical element. |
| ESPHome `set_retry` | Deprecated 2026.2.0, removed 2026.8.0. Do not introduce it. |
| `esphome-state-machine` external component | The existing hand-rolled `InjectorPhase` enum + switch-based state machine is simpler, more debuggable, and already working. Adding an external YAML-driven state machine component would require refactoring proven code for no benefit. |

**Retry architecture recommendation:**

Add retry logic inside `ButtonInjector` itself:

```
finish_sequence_(TIMEOUT) currently:
  -> clears known_setpoint_
  -> transitions to COOLDOWN

finish_sequence_(TIMEOUT) with retry:
  -> if retry_count_ < max_retries_ (default: 2):
       increment retry_count_
       re-enter PROBING (since known_setpoint_ is now NAN)
  -> else:
       publish FAILED to HA
       transition to COOLDOWN
       reset retry_count_
```

This keeps all retry logic in C++ on the ESP32 (no HA automation round-trips needed) and uses the existing state machine phases. The retry count and final result should be published to HA via a new `sensor` (numeric: `command_success_rate`) and the existing `text_sensor` (state string like `"failed:104:2retries"`).

### 2. Data Export Pipeline (Python-Side, Dev Machine)

The goal is getting time-series data from HA's SQLite recorder onto the dev machine for Jupyter/pandas analysis.

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `requests` | >=2.32.5 | HTTP client for HA REST API | Standard, already widely used. The HA REST API `/api/history/period/<timestamp>` endpoint with `filter_entity_id`, `minimal_response`, and `no_attributes` params is the simplest path for bulk export. |
| `pandas` | >=2.3.0 (or 3.0.2 if on Python 3.11+) | Time-series analysis and DataFrame operations | Already used in `scripts/analyze_heating.py`. Pin to >=2.3.0 for broad compatibility; 3.0.2 is fine since project already requires Python >=3.11. |
| `matplotlib` | >=3.10.0 | Plotting (scatter, time-series, correlation) | Already used in `scripts/analyze_heating.py` for `--plot` mode. |
| Long-Lived Access Token | N/A (HA config) | Authentication for REST API calls | Generated at `http://<HA_IP>:8123/profile`. Store in `.env` file (gitignored) or pass as CLI arg. |

**Two viable approaches, with recommendation:**

| Approach | Pros | Cons | Recommendation |
|----------|------|------|----------------|
| **A: SCP the SQLite DB** | Full data, offline analysis, already proven in `analyze_heating.py` | Requires SSH/Samba to RPi, DB locked during HA writes, must copy ~50-200MB file | Keep as fallback for deep analysis |
| **B: HA REST API** | No SSH needed, query specific entities/time ranges, lighter payloads, scriptable | Limited to recorder retention (~10 days default), no long-term statistics via REST, HTTP overhead | **Use for operational monitoring** |
| C: WebSocket API | Real-time streaming, lower per-message overhead | Overkill for batch export, more complex client code, no history endpoint | Skip |
| D: `homeassistant_api` wrapper lib | Nicer Python API | Extra dependency for little benefit over raw `requests` | Skip |
| E: `HASS-data-detective` | Pre-built analysis tools | Unmaintained, adds dep chain, we already have custom analysis | Skip |

**Recommendation: Use BOTH A and B.** SCP for deep historical analysis (the existing `analyze_heating.py` pattern), REST API for a new lightweight `scripts/export_ha_data.py` that pulls recent data on demand.

The REST API script pattern:

```python
# scripts/export_ha_data.py
# Usage: uv run scripts/export_ha_data.py --entity sensor.tublemetry_hot_tub_temperature --days 7
import requests
import pandas as pd

HA_URL = os.environ["HA_URL"]  # e.g. http://homeassistant.local:8123
HA_TOKEN = os.environ["HA_TOKEN"]

response = requests.get(
    f"{HA_URL}/api/history/period/{start_time}",
    headers={"Authorization": f"Bearer {HA_TOKEN}"},
    params={
        "filter_entity_id": entity_id,
        "end_time": end_time,
        "minimal_response": "",
        "no_attributes": "",
    },
)
```

**Key limitation:** The REST API `/api/history/period/` is limited to the recorder's short-term retention window (default 10 days, configurable). For data older than that, you must use the SCP+SQLite approach or configure HA's recorder to retain longer:

```yaml
# configuration.yaml on HA
recorder:
  purge_keep_days: 30
```

### 3. Enphase Power Monitoring Integration (HA-Side)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Enphase Envoy core integration | Built into HA Core | Exposes whole-home power consumption as `sensor.envoy_<SERIAL>_current_power_consumption` (Watts) | Already a core HA integration, auto-discovered on LAN. No custom integration needed. Polls every 60 seconds by default. |
| HA template sensor | Built into HA | Derive heater power draw by differencing consumption during heater-on vs heater-off windows | The hot tub heater is 4kW (240V). When `binary_sensor.tublemetry_hot_tub_heater` transitions on->off or off->on, the whole-home power delta should be ~4000W. A template sensor can detect this correlation. |
| `pandas` (dev machine) | >=2.3.0 | Offline correlation analysis: overlay Enphase power data with heater state binary sensor | Export both sensors via REST API or SCP, merge on timestamp, compute correlation. |

**Entity discovery pattern for Enphase:**

The Enphase integration creates entities named `sensor.envoy_<SERIAL>_<metric>`. The serial number is the Envoy's hardware serial. Key entities for this project:

| Entity Pattern | Unit | Update Rate | Purpose |
|----------------|------|-------------|---------|
| `sensor.envoy_<SN>_current_power_consumption` | W | 60s | Whole-home consumption including hot tub |
| `sensor.envoy_<SN>_current_power_production` | W | 60s | Solar production (useful for net calculation) |
| `sensor.envoy_<SN>_lifetime_energy_consumption` | Wh | 60s | Cumulative energy (state_class: total_increasing) |
| `sensor.envoy_<SN>_lifetime_energy_production` | Wh | 60s | Cumulative solar energy |

**CT clamp requirement:** Consumption monitoring requires a hardware CT clamp on the Envoy. Production monitoring works without CTs if microinverters are reporting. Verify the user's Envoy has consumption CTs installed.

**Heater validation template sensor (HA-side):**

```yaml
template:
  - sensor:
      - name: "Hot Tub Heater Power Estimate"
        unit_of_measurement: "W"
        state_class: measurement
        device_class: power
        state: >
          {% set consumption = states('sensor.envoy_SERIAL_current_power_consumption') | float(0) %}
          {% set heater_on = is_state('binary_sensor.tublemetry_hot_tub_heater', 'on') %}
          {# This is a placeholder -- actual implementation needs baseline subtraction #}
          {# Real approach: track consumption baseline when heater is off, subtract from current #}
          {{ consumption if heater_on else 0 }}
```

The actual heater power estimation is better done as offline analysis first (Python correlation script) before attempting a real-time HA template. The 60-second Enphase polling and the 1F temperature quantization make real-time correlation noisy.

**What NOT to add (Enphase-side):**

| Rejected | Why |
|----------|-----|
| Custom Enphase integration (HACS) | The core integration provides all needed entities. HACS alternatives (`home_assistant_custom_envoy`, `enphase_envoy_installer`) add inverter-level and installer-level features not needed for whole-home power monitoring. |
| Direct Envoy local API access | The HA integration already polls the Envoy locally every 60s. Adding a separate Python script to poll the Envoy API would duplicate data collection and risk rate-limiting. |
| Enphase Cloud API | Unnecessary. The Envoy is on the local LAN and the HA integration uses local polling (with cloud auth for token refresh on firmware >=7.0). |

### 4. Safety & Signal Processing Paradigms (Coding Discipline, Not Libraries)

This section is about applying IEC 61508-inspired thinking as **coding patterns**, not adding safety-certified tooling to a home automation project.

| Concept | How It Applies | Implementation |
|---------|---------------|----------------|
| Command-verify-retry | Already architected in `ButtonInjector`. Add retry loop (see section 1). | C++ in `button_injector.cpp` |
| Defensive state transitions | Every state machine transition should validate preconditions. Already partially done (bounds checking in `request_temperature()`). | Add assertions/checks at each `transition_to_()` call |
| Safe state on failure | After max retries exhausted, the system should surface the failure and NOT silently accept a wrong setpoint. The Balboa controller itself is the safety backstop. | Publish `FAILED` to HA, leave `known_setpoint_` as NAN (forces re-probe on next attempt) |
| Watchdog/heartbeat | ESPHome already has `reboot_timeout` for WiFi (10min) and API (15min). Add a software watchdog for the display decode pipeline -- if no valid frame in N minutes, publish `stale` state. | New `timeout` filter or lambda check in `loop()` |
| Sensor fusion | Correlate: (a) display-decoded temperature, (b) heater binary state, (c) Enphase power. If heater shows "on" but Enphase shows no 4kW spike, flag anomaly. | Python-side analysis first, then HA automation if pattern proves reliable |
| Graceful degradation | If display decode fails, TOU should continue with last-known-good setpoint (not crash). If Enphase is unavailable, heater validation degrades to display-only. | HA automation conditions checking sensor availability |

**What NOT to add (safety-side):**

| Rejected | Why |
|----------|-----|
| Formal Kalman filter for temperature | Display temperature is a decoded 3-digit integer. The "noise" is decode errors (wrong 7-segment lookup), not Gaussian sensor noise. The stability filter (3 consecutive identical frames) is the correct denoising approach. Kalman would smooth between valid readings, which is wrong -- you want to reject bad frames, not average them. |
| MISRA-C static analysis tools (PC-lint, Polyspace) | Cost, complexity, and certification overhead are wildly disproportionate. This ESP32 simulates button presses; it cannot directly energize the heater. The Balboa controller has its own high-limit safety switch (hardware). Apply MISRA principles (no dynamic allocation in ISR, bounded loops, explicit error handling) as code review discipline. |
| Redundant hardware (dual ESP32) | Single installation, non-safety-critical application. The thermal runaway automation in HA is the safety layer, and the Balboa controller's own thermostat + high-limit switch are the hardware safety layers. |
| IEC 61508 SIL rating | This is a home automation project, not an industrial safety system. Borrowing the thinking (hazard analysis, safe states, diagnostic coverage) is valuable; pursuing formal certification is not. |

## Existing Stack (No Changes Needed)

These are already in place and validated. Listed for completeness.

| Technology | Version | Purpose | Status |
|------------|---------|---------|--------|
| ESP32 WROOM-32 | N/A | Microcontroller (520KB SRAM, ~100-150KB free heap with ESPHome+WiFi) | Deployed |
| ESPHome | 2026.3.1 (current) | Firmware framework, native HA integration | Update to latest stable |
| Arduino framework | Via ESPHome | Hardware abstraction | No change |
| AQY212EH photorelays | N/A | Galvanic-isolated button injection | Deployed |
| Home Assistant OS | Latest | Automation platform, RPi4 | Running |
| Python 3.11+ | 3.11 | Decode library, analysis scripts | In use |
| pytest | >=9.0.2 | Test framework (391 tests for decode library) | In use |
| SQLite (HA recorder) | Built-in | Time-series storage | In use |
| `uv` | Latest | Python package/env management | In use |

## New Python Dependencies

Add to `pyproject.toml` under a new dependency group for analysis scripts:

```toml
[dependency-groups]
dev = [
    "pytest>=9.0.2",
    "pyyaml>=6.0",
]
analysis = [
    "pandas>=2.3.0",
    "matplotlib>=3.10.0",
    "requests>=2.32.5",
]
```

Then install with: `uv sync --group analysis`

**Note:** `pandas` and `matplotlib` are already imported in `scripts/analyze_heating.py` but are not declared as dependencies. This formalizes them.

## Integration Points with Existing ESPHome Component

The new features touch the existing C++ component at specific, bounded points:

| File | Change Type | What Changes |
|------|-------------|-------------|
| `button_injector.h` | Add members | `uint8_t retry_count_{0}`, `uint8_t max_retries_{2}`, new `sensor::Sensor *command_success_sensor_` |
| `button_injector.cpp` | Modify `finish_sequence_()` | Add retry branch on TIMEOUT before transitioning to COOLDOWN |
| `button_injector.cpp` | New method | `publish_result_()` to emit structured result string to text_sensor |
| `tublemetry_display.h` | Add member | `uint32_t last_valid_frame_ms_{0}` for decode staleness detection |
| `tublemetry_display.cpp` | Modify `process_frame_()` | Update `last_valid_frame_ms_` on successful decode |
| `tublemetry_display.cpp` | Modify `loop()` | Check frame staleness, publish warning if stale > threshold |
| `tublemetry.yaml` | Add entities | New sensors for command success rate, injection result details |

## ESP32 Memory Budget

The ESP32 WROOM-32 has ~100-150KB free heap with ESPHome + WiFi + the current component. The proposed additions are minimal:

| Addition | Estimated Heap Cost | Notes |
|----------|-------------------|-------|
| Retry counter + max retries | ~16 bytes | Two uint8_t members |
| Success rate sensor | ~200 bytes | ESPHome sensor object |
| Result text sensor (extended) | ~0 bytes | Reuses existing injection_state_sensor_ |
| Frame staleness tracking | ~8 bytes | One uint32_t member |
| **Total** | **~224 bytes** | Negligible vs 100KB+ free heap |

No new libraries, no dynamic allocation changes, no heap pressure concern.

## Sources

### HIGH Confidence (official docs, verified)
- [Home Assistant REST API](https://developers.home-assistant.io/docs/api/rest/) -- history/period endpoint, auth, params
- [Enphase Envoy Integration](https://www.home-assistant.io/integrations/enphase_envoy/) -- entity patterns, CT requirements, firmware versions
- [ESPHome Sensor Filters](https://esphome.io/components/sensor/) -- built-in filter catalog
- [ESPHome set_retry Deprecation](https://developers.esphome.io/blog/2026/02/12/set_retry-deprecated-use-set_timeout-or-set_interval-instead/) -- deprecated 2026.2.0, removed 2026.8.0
- [ESPHome Component Class](https://esphome.io/api/classesphome_1_1_component) -- set_timeout, set_interval API
- [ESP-IDF Memory Types](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/memory-types.html) -- ESP32 SRAM layout
- [ESPHome 2026.3.0 Release](https://esphome.io/changelog/2026.3.0/) -- current stable version

### MEDIUM Confidence (official + community verified)
- [HA Community: Extracting Data from HA DB](https://community.home-assistant.io/t/extracting-data-from-ha-database-for-further-data-analysis/571584) -- SCP + pandas workflow
- [HA Community: Long-Term Statistics REST API](https://community.home-assistant.io/t/can-i-get-long-term-statistics-from-the-rest-api/761444) -- confirms REST API limitation to short-term data
- [Enphase Envoy Community Issues](https://github.com/home-assistant/core/issues/82879) -- power sensor entity naming and state_class

### LOW Confidence (needs validation)
- Enphase Envoy polling frequency is configurable below 60s -- community reports but not in official docs
- HA REST API hard limit at 10 days -- community reports vary between 3-10 days depending on recorder config
- Exact free heap on this specific ESP32 with current firmware -- need to check via ESPHome `debug` component sensor
