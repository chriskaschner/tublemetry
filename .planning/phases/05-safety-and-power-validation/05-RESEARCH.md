# Phase 5: Safety and Power Validation - Research

**Researched:** 2026-04-12
**Domain:** Home Assistant automation YAML (graduated triggers, input_boolean coordination, stale data gating), Enphase power monitoring integration
**Confidence:** HIGH

## Summary

Phase 5 replaces the current all-or-nothing thermal runaway automation with a graduated three-tier response, adds TOU-runaway oscillation prevention via a shared `input_boolean` flag, gates all safety automations on ESP32 online status, and creates an independent heater-on binary sensor derived from Enphase whole-home power consumption.

The existing codebase provides strong patterns to follow. The drift detection automation (`ha/drift_detection.yaml`) and its test suite (`tests/test_drift_detection.py`) establish a YAML-validation test pattern that maps directly to new automations. The thermal runaway automation (`ha/thermal_runaway.yaml`) provides the template trigger + `for:` duration pattern that the graduated version will extend. The TOU automation (`ha/tou_automation.yaml`) already uses a `choose:` action block with trigger IDs -- the same pattern applies to the graduated thermal runaway.

The Enphase power detection (PWR-01) has the most uncertainty. The user's STATE.md flags "Enphase CT clamp installation unverified -- must confirm before Phase 5 planning." The CONTEXT.md decision D-13 addresses this with a fallback: create a stub binary sensor if the Enphase API is unavailable. The recommended approach uses Home Assistant's built-in Enphase Envoy integration, which provides `sensor.envoy_*_current_power_consumption` at 60-second update intervals.

**Primary recommendation:** Implement SAFE-01/02/03 first (pure HA automation YAML with no external dependencies), then PWR-01 last with the stub fallback pattern. Use the existing test_drift_detection.py YAML validation pattern for all new automation files.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Graduated Thermal Runaway Response (SAFE-01):**
- D-01: Three tiers -- Warning (2-4F, log+notify only), Moderate (4-6F, proportional setpoint reduction, set runaway flag), Severe (>6F, drop to 80F floor, disable TOU)
- D-02: All tiers sustain for 5 minutes before acting
- D-03: Current thermal_runaway.yaml is replaced (not extended)
- D-04: Each tier has its own notification_id (thermal_warning, thermal_moderate, thermal_severe)

**TOU-Runaway Oscillation Prevention (SAFE-02):**
- D-05: Create input_boolean.thermal_runaway_active HA helper
- D-06: TOU automation adds condition: skip setpoint raise if thermal_runaway_active is on
- D-07: Moderate tier auto-clears flag when temp <= setpoint
- D-08: Severe tier requires manual re-enable

**Stale Data Gating (SAFE-03):**
- D-09: Use ESPHome built-in status binary_sensor for offline detection
- D-10: Gate thermal runaway and TOU on ESP32 online status; drift detection already handles unknown/unavailable
- D-11: On offline: persistent notification, disable TOU schedule
- D-12: New file ha/stale_data.yaml; on recovery notify user but do NOT auto-re-enable TOU

**Enphase Heater Detection (PWR-01):**
- D-13: Include with fallback -- stub binary sensor if Enphase API unavailable
- D-14: Safety features do NOT depend on PWR-01
- D-15: Heater detection algorithm is Claude's discretion
- D-16: Expose as binary_sensor.hot_tub_heater_power (separate from display heater bit)

### Claude's Discretion
- Warning tier (2-4F): whether to set input_boolean flag or just log+notify
- Heater detection algorithm (threshold vs derivative)
- Enphase API integration approach (REST sensor vs HA integration)
- Automation YAML structure (single graduated file vs separate per-tier files)
- Whether stale data automation should have a re-enable grace period

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SAFE-01 | Graduated thermal runaway response (warning, partial reduction, floor drop) | Multi-trigger template automation with trigger IDs and choose: action block -- HA natively supports this pattern; existing thermal_runaway.yaml provides the base template |
| SAFE-02 | TOU-runaway oscillation prevention (runaway cooldown flag blocks TOU raise) | input_boolean helper entity with state condition gating in TOU automation -- standard HA pattern, verified in official docs |
| SAFE-03 | Stale data gating (refuse to act on last-known values when ESP32 offline) | ESPHome status binary_sensor entity (binary_sensor.tublemetry_hot_tub_api_status) transitions to off/unavailable on disconnect; automation triggers on state change |
| PWR-01 | Independent heater state via Enphase power consumption (4kW step detection) | Enphase Envoy integration provides sensor.envoy_*_current_power_consumption at 60s intervals; threshold binary sensor or template binary sensor for step detection |

</phase_requirements>

## Project Constraints (from CLAUDE.md / global instructions)

- Python tooling uses `uv` for environment and package management
- Tests must be written to verify work; tests precede features
- Never include "Co-Authored-By" trailer in git commits
- Never use emojis in output
- Write decisions and rationale to WORKLOG.md immediately

## Standard Stack

### Core
| Library/Tool | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Home Assistant | 2025.x+ | Automation engine, entity management | Already running on user's RPi4 [VERIFIED: project codebase] |
| ESPHome | 2024.x+ | ESP32 firmware, binary_sensor.status platform | Already deployed, status entity configured [VERIFIED: esphome/tublemetry.yaml] |
| PyYAML | >=6.0 | YAML parsing in tests | Already in dev dependencies [VERIFIED: pyproject.toml] |
| pytest | >=9.0.2 | Test framework | Already in dev dependencies [VERIFIED: pyproject.toml] |

### Supporting
| Library/Tool | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| HA Enphase Envoy integration | built-in | Power consumption data | PWR-01 sensor source (if Enphase available) |
| HA input_boolean integration | built-in | Shared coordination flag | SAFE-02 oscillation prevention |
| HA threshold integration | built-in | Binary sensor from numeric threshold | PWR-01 heater detection (option) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Enphase integration | REST sensor polling local API | More control over endpoints but requires token management; integration handles auth automatically |
| Threshold binary sensor | Template binary sensor | Template gives more flexibility for complex logic but threshold is simpler for a single-value comparison |
| Single graduated automation | Separate automation per tier | Separate files are cleaner to test individually but create more files; single file with choose: is more maintainable |

## Architecture Patterns

### Recommended Project Structure
```
ha/
  thermal_runaway.yaml      # REPLACED: graduated 3-tier version
  tou_automation.yaml       # MODIFIED: add input_boolean condition
  stale_data.yaml           # NEW: ESP32 offline detection + gating
  heater_power.yaml         # NEW: Enphase-derived heater binary sensor
  drift_detection.yaml      # UNCHANGED
  heating_tracker.yaml      # UNCHANGED
tests/
  test_thermal_runaway.py   # REWRITTEN: tests for graduated version
  test_tou_automation.py    # NEW: verify oscillation prevention condition
  test_stale_data.py        # NEW: stale data automation validation
  test_heater_power.py      # NEW: heater power sensor validation
```

### Pattern 1: Multi-Tier Template Trigger with Trigger IDs
**What:** Single automation with multiple template triggers, each having an `id`, and a `choose:` action block that dispatches based on which trigger fired.
**When to use:** Graduated response automations where different thresholds lead to different actions (SAFE-01).
**Example:**
```yaml
# Source: HA official docs - Automation Trigger
# [CITED: https://www.home-assistant.io/docs/automation/trigger/]
trigger:
  - platform: template
    value_template: >
      {{ states('sensor.tublemetry_hot_tub_temperature') | float(0) >
         states('number.tublemetry_hot_tub_setpoint') | float(999) + 6 }}
    for:
      minutes: 5
    id: severe
  - platform: template
    value_template: >
      {{ states('sensor.tublemetry_hot_tub_temperature') | float(0) >
         states('number.tublemetry_hot_tub_setpoint') | float(999) + 4 }}
    for:
      minutes: 5
    id: moderate
  - platform: template
    value_template: >
      {{ states('sensor.tublemetry_hot_tub_temperature') | float(0) >
         states('number.tublemetry_hot_tub_setpoint') | float(999) + 2 }}
    for:
      minutes: 5
    id: warning

action:
  - choose:
      - conditions:
          - condition: trigger
            id: severe
        sequence:
          # ... severe response actions
      - conditions:
          - condition: trigger
            id: moderate
        sequence:
          # ... moderate response actions
    default:
      # ... warning response actions
```

**Critical ordering note:** HA evaluates template triggers top-to-bottom and fires on the FIRST match. When temp is 8F over setpoint, all three triggers evaluate to true. Place SEVERE first so it matches before moderate/warning. [VERIFIED: HA docs state "the automation will start when any of these triggers trigger" -- triggers are evaluated independently, but with `for:` durations, the first to satisfy both condition AND duration wins in `mode: single`] [ASSUMED: trigger ordering matters for `mode: single` automations -- need to verify whether HA fires the most-specific trigger or the first-listed one when multiple are simultaneously true]

### Pattern 2: input_boolean as Cross-Automation Coordination Flag
**What:** Use `input_boolean` entity as a shared flag between automations. One automation sets it; another checks it as a condition.
**When to use:** SAFE-02 oscillation prevention.
**Example:**
```yaml
# Source: HA official docs - Input Boolean
# [CITED: https://www.home-assistant.io/integrations/input_boolean/]

# In thermal runaway (setter):
action:
  - action: input_boolean.turn_on
    target:
      entity_id: input_boolean.thermal_runaway_active

# In TOU automation (checker):
condition:
  - condition: state
    entity_id: input_boolean.thermal_runaway_active
    state: "off"
```

### Pattern 3: ESPHome Status Binary Sensor for Offline Gating
**What:** ESPHome's `binary_sensor: platform: status` reports `on` when device is connected via native API, `off` when disconnected. HA shows it as `unavailable` when no connection exists.
**When to use:** SAFE-03 stale data detection.
**Entity name in this project:** `binary_sensor.tublemetry_hot_tub_api_status` [VERIFIED: ESPHome naming convention: {device_name}_{sensor_name_slugified}; device name is "tublemetry", sensor name is "Hot Tub API Status" per esphome/tublemetry.yaml line 98]
**Example:**
```yaml
# Source: ESPHome docs - Status Binary Sensor
# [CITED: https://esphome.io/components/binary_sensor/status/]
trigger:
  - platform: state
    entity_id: binary_sensor.tublemetry_hot_tub_api_status
    to: "off"
  - platform: state
    entity_id: binary_sensor.tublemetry_hot_tub_api_status
    to: "unavailable"
```

**Important correction:** The CONTEXT.md code_context section refers to `binary_sensor.tublemetry_hot_tub_status` but the actual entity name is `binary_sensor.tublemetry_hot_tub_api_status` based on the ESPHome config (`name: "Hot Tub API Status"`). The project's own HA-SETUP-GUIDE.md confirms this as `binary_sensor.hot_tub_api_status` (without the tublemetry prefix, which may vary based on how HA registers the entity). The planner should verify the exact entity ID against the live HA instance during execution.

### Pattern 4: Template Binary Sensor for Power Step Detection (PWR-01)
**What:** A trigger-based template binary sensor that turns on when whole-home power exceeds a threshold, indicating the 4kW heater is running.
**When to use:** PWR-01 Enphase heater detection.
**Example:**
```yaml
# Simple threshold approach (recommended for 60s update interval)
# [ASSUMED: Enphase power consumption entity name follows
#  sensor.envoy_{serial}_current_power_consumption pattern]
template:
  - binary_sensor:
      - name: "Hot Tub Heater Power"
        state: >
          {{ states('sensor.envoy_SERIAL_current_power_consumption') | float(0) > 3500 }}
        device_class: power
        delay_on:
          seconds: 60
        delay_off:
          seconds: 120
```

### Anti-Patterns to Avoid
- **Testing HA automation logic at runtime:** HA automations cannot be unit-tested for runtime behavior. Validate YAML structure, entity references, and action ordering only -- do not attempt to simulate HA's template engine in Python.
- **Auto-re-enabling safety features:** After a safety event or ESP32 recovery, never auto-re-enable TOU or clear severe runaway flags. Always require manual user intervention (D-08, D-12).
- **Comparing boolean states with `true`/`false`:** In HA templates, input_boolean states are string `'on'`/`'off'`, NOT Python booleans. Use `states('input_boolean.x') == 'on'` or use `is_state('input_boolean.x', 'on')`. [CITED: https://community.home-assistant.io/t/how-to-check-for-boolean-input-in-if-condition/868902]
- **Using `float()` without safe defaults:** Always use `float(0)` for temperature (0F is safe-low, won't trigger overshoot) and `float(999)` for setpoint (999F is safe-high, won't trigger). Already established in current thermal_runaway.yaml. [VERIFIED: ha/thermal_runaway.yaml line 21]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| ESP32 offline detection | Custom timeout/heartbeat logic | ESPHome `binary_sensor: platform: status` | ESPHome handles disconnect detection internally; HA marks entity unavailable automatically [CITED: https://esphome.io/components/binary_sensor/status/] |
| Power consumption data | Custom Enphase API polling | HA Enphase Envoy integration | Handles token auth, firmware version differences, and entity management [CITED: https://www.home-assistant.io/integrations/enphase_envoy/] |
| Cross-automation state | Template sensors or global variables | `input_boolean` helper | Survives HA restarts, has built-in UI toggle, standard condition pattern [CITED: https://www.home-assistant.io/integrations/input_boolean/] |
| Numeric threshold to binary | Custom template with state tracking | HA `threshold` integration or template binary_sensor with delay_on/delay_off | Built-in hysteresis support prevents flapping [CITED: https://www.home-assistant.io/integrations/threshold/] |

## Common Pitfalls

### Pitfall 1: Trigger Ordering in mode: single Automations
**What goes wrong:** When temperature is 8F over setpoint, all three tier triggers (warning, moderate, severe) evaluate to true simultaneously. If warning is listed first in a `mode: single` automation, it fires and blocks moderate/severe.
**Why it happens:** HA template triggers fire independently. In `mode: single`, only the first trigger to fire gets to execute. With `for: minutes: 5`, all three could satisfy at the same moment.
**How to avoid:** List triggers from most-severe to least-severe (severe first, warning last). Alternatively, use a single trigger with the lowest threshold and compute the tier in the action block using choose conditions with value comparisons.
**Warning signs:** Warning notification fires but no setpoint change occurs even at 8F overshoot.

### Pitfall 2: Template Trigger Simultaneous Re-evaluation
**What goes wrong:** After a moderate tier event reduces the setpoint proportionally, the temperature may still be 2F above the new setpoint, immediately re-triggering the warning tier.
**Why it happens:** When moderate action changes the setpoint, the template triggers re-evaluate. If temp is now 3F above the new setpoint, the warning trigger becomes true (but needs to sustain 5 min).
**How to avoid:** This is actually desired behavior -- the warning tier is a monitoring-only notification and does not conflict. The 5-minute sustain window prevents immediate re-triggering. The `mode: single` flag prevents concurrent execution.
**Warning signs:** Stacking warning notifications after a moderate event. Use notification_id to overwrite instead of stack (already decided in D-04).

### Pitfall 3: input_boolean State Persistence Across Restarts
**What goes wrong:** After an HA restart, `input_boolean.thermal_runaway_active` restores to its pre-restart state. If it was `on` before restart, TOU remains blocked after restart even if the thermal event resolved.
**Why it happens:** `input_boolean` restores last state by default (no `initial` config).
**How to avoid:** This is actually the SAFE behavior -- better to leave TOU blocked and require manual check than to auto-clear. Document in user-facing notification that manual re-enable is required.
**Warning signs:** TOU not running after HA restart when no active thermal event exists.

### Pitfall 4: Moderate Tier Auto-Clear Race Condition (D-07)
**What goes wrong:** The moderate tier sets `input_boolean.thermal_runaway_active` to `on` and reduces setpoint. The auto-clear condition (temp <= setpoint) fires before the physical tub has actually cooled -- just because the NEW lower setpoint is now closer to current temp.
**Why it happens:** Proportional reduction (e.g., from 104 to 99 when 5F over) means the current temp (109F) is still far above the new setpoint (99F). The auto-clear won't trigger until 109 drops to 99 or below. This is correct by design.
**How to avoid:** The proportional reduction already handles this naturally. The auto-clear should be a separate automation that watches for `temp <= setpoint AND input_boolean.thermal_runaway_active is on`.
**Warning signs:** If the auto-clear is implemented as an inline template condition within the thermal runaway automation itself (wrong -- it should be a separate automation or trigger).

### Pitfall 5: ESPHome Status Entity Name Mismatch
**What goes wrong:** Automation references `binary_sensor.tublemetry_hot_tub_status` but the actual entity is `binary_sensor.tublemetry_hot_tub_api_status`.
**Why it happens:** The CONTEXT.md code_context section mentions `binary_sensor.tublemetry_hot_tub_status` but the ESPHome config names it "Hot Tub API Status" which slugifies to `hot_tub_api_status`.
**How to avoid:** Verify the exact entity ID. The ESPHome config at `esphome/tublemetry.yaml` line 98 shows `name: "Hot Tub API Status"` under `platform: status`. Combined with device name `tublemetry`, the full entity ID is `binary_sensor.tublemetry_hot_tub_api_status`.
**Warning signs:** Automation never triggers because entity_id doesn't exist in HA.

### Pitfall 6: Enphase Power Sensor Update Frequency
**What goes wrong:** The 4kW heater step detection misses short heating cycles because the Enphase integration only updates every 60 seconds.
**Why it happens:** Enphase Envoy integration default polling interval is 60 seconds [CITED: https://www.home-assistant.io/integrations/enphase_envoy/]. A heater cycle shorter than 60 seconds could be missed entirely.
**How to avoid:** Accept this as a known limitation. Hot tub heater cycles are typically 15-45 minutes, so 60-second granularity is sufficient. Use `delay_off` on the binary sensor to prevent flickering off between polls.
**Warning signs:** Heater power binary sensor shows off even when the tub is actively heating.

## Code Examples

### Graduated Thermal Runaway (SAFE-01) -- Structural Pattern
```yaml
# Source: existing ha/thermal_runaway.yaml pattern + HA trigger docs
# [VERIFIED: ha/thermal_runaway.yaml, CITED: https://www.home-assistant.io/docs/automation/trigger/]

alias: Hot Tub Thermal Runaway Protection
mode: single

trigger:
  # SEVERE: >6F over for 5 min -- listed first for priority
  - platform: template
    value_template: >
      {{ states('sensor.tublemetry_hot_tub_temperature') | float(0) >
         states('number.tublemetry_hot_tub_setpoint') | float(999) + 6 }}
    for:
      minutes: 5
    id: severe

  # MODERATE: 4-6F over for 5 min
  - platform: template
    value_template: >
      {{ states('sensor.tublemetry_hot_tub_temperature') | float(0) >
         states('number.tublemetry_hot_tub_setpoint') | float(999) + 4 }}
    for:
      minutes: 5
    id: moderate

  # WARNING: 2-4F over for 5 min
  - platform: template
    value_template: >
      {{ states('sensor.tublemetry_hot_tub_temperature') | float(0) >
         states('number.tublemetry_hot_tub_setpoint') | float(999) + 2 }}
    for:
      minutes: 5
    id: warning

condition:
  - condition: template
    value_template: >
      {{ states('sensor.tublemetry_hot_tub_temperature') not in ['unknown', 'unavailable']
         and states('number.tublemetry_hot_tub_setpoint') not in ['unknown', 'unavailable'] }}
  # Gate on ESP32 online (SAFE-03 coordination)
  - condition: state
    entity_id: binary_sensor.tublemetry_hot_tub_api_status
    state: "on"

action:
  - choose:
      - conditions:
          - condition: trigger
            id: severe
        sequence:
          # 1. Log
          - action: system_log.write
            data:
              message: >
                THERMAL RUNAWAY SEVERE: ...
              level: error
              logger: tubtron.thermal_runaway
          # 2. Notify
          - action: persistent_notification.create
            data:
              title: "THERMAL RUNAWAY SEVERE"
              message: "..."
              notification_id: thermal_severe
          # 3. Set runaway flag
          - action: input_boolean.turn_on
            target:
              entity_id: input_boolean.thermal_runaway_active
          # 4. Disable TOU
          - action: automation.turn_off
            target:
              entity_id: automation.hot_tub_tou_schedule
          # 5. Drop to floor
          - action: number.set_value
            target:
              entity_id: number.tublemetry_hot_tub_setpoint
            data:
              value: 80

      - conditions:
          - condition: trigger
            id: moderate
        sequence:
          # 1. Log
          - action: system_log.write
            data:
              message: >
                THERMAL RUNAWAY MODERATE: ...
              level: warning
              logger: tubtron.thermal_runaway
          # 2. Notify
          - action: persistent_notification.create
            data:
              title: "THERMAL RUNAWAY MODERATE"
              message: "..."
              notification_id: thermal_moderate
          # 3. Set runaway flag
          - action: input_boolean.turn_on
            target:
              entity_id: input_boolean.thermal_runaway_active
          # 4. Proportional reduction
          - action: number.set_value
            target:
              entity_id: number.tublemetry_hot_tub_setpoint
            data:
              value: >
                {{ [states('number.tublemetry_hot_tub_setpoint') | float -
                   (states('sensor.tublemetry_hot_tub_temperature') | float -
                    states('number.tublemetry_hot_tub_setpoint') | float), 80] | max | int }}

    # DEFAULT: warning tier
    default:
      - action: system_log.write
        data:
          message: >
            THERMAL WARNING: ...
          level: warning
          logger: tubtron.thermal_runaway
      - action: persistent_notification.create
        data:
          title: "THERMAL WARNING"
          message: "..."
          notification_id: thermal_warning
```

### TOU Condition Addition (SAFE-02)
```yaml
# Source: existing ha/tou_automation.yaml -- add to condition block
# [VERIFIED: ha/tou_automation.yaml has empty conditions: []]
condition:
  - condition: state
    entity_id: input_boolean.thermal_runaway_active
    state: "off"
```

### Stale Data Automation (SAFE-03) -- Structural Pattern
```yaml
# Source: ESPHome status sensor docs + drift_detection.yaml pattern
# [CITED: https://esphome.io/components/binary_sensor/status/]

alias: Hot Tub ESP32 Offline Detection
mode: single

trigger:
  - platform: state
    entity_id: binary_sensor.tublemetry_hot_tub_api_status
    to: "off"
    id: offline
  - platform: state
    entity_id: binary_sensor.tublemetry_hot_tub_api_status
    to: "unavailable"
    id: offline
  - platform: state
    entity_id: binary_sensor.tublemetry_hot_tub_api_status
    to: "on"
    id: online

action:
  - choose:
      - conditions:
          - condition: trigger
            id: offline
        sequence:
          - action: persistent_notification.create
            data:
              title: "ESP32 OFFLINE"
              message: "Hot tub ESP32 lost connection. Safety automations suspended."
              notification_id: esp32_offline
          - action: automation.turn_off
            target:
              entity_id: automation.hot_tub_tou_schedule
    default:
      # Online recovery
      - action: persistent_notification.create
        data:
          title: "ESP32 ONLINE"
          message: "Hot tub ESP32 reconnected. TOU schedule NOT auto-re-enabled."
          notification_id: esp32_online
```

### Moderate Tier Auto-Clear (SAFE-02 D-07)
```yaml
# Separate automation for clearing moderate runaway flag
alias: Hot Tub Thermal Runaway Clear
mode: single

trigger:
  - platform: template
    value_template: >
      {{ states('sensor.tublemetry_hot_tub_temperature') | float(999) <=
         states('number.tublemetry_hot_tub_setpoint') | float(0) }}
    for:
      minutes: 2

condition:
  - condition: state
    entity_id: input_boolean.thermal_runaway_active
    state: "on"

action:
  - action: input_boolean.turn_off
    target:
      entity_id: input_boolean.thermal_runaway_active
  - action: persistent_notification.create
    data:
      title: "THERMAL RUNAWAY CLEARED"
      message: "Temperature returned to setpoint. Runaway flag cleared."
      notification_id: thermal_cleared
```

### Test Pattern -- YAML Validation
```python
# Source: existing tests/test_drift_detection.py pattern
# [VERIFIED: tests/test_drift_detection.py]

import pytest
import yaml
from pathlib import Path

RUNAWAY_FILE = Path(__file__).parent.parent / "ha" / "thermal_runaway.yaml"

@pytest.fixture
def config():
    return yaml.safe_load(RUNAWAY_FILE.read_text())

class TestGraduatedThermalRunaway:
    def test_has_three_triggers(self, config):
        assert len(config["trigger"]) == 3

    def test_trigger_ids_present(self, config):
        ids = {t["id"] for t in config["trigger"]}
        assert ids == {"severe", "moderate", "warning"}

    def test_severe_listed_first(self, config):
        assert config["trigger"][0]["id"] == "severe"

    def test_all_triggers_have_5min_sustain(self, config):
        for t in config["trigger"]:
            assert t["for"]["minutes"] == 5

    def test_choose_has_severe_and_moderate(self, config):
        # ... validate choose block structure
        pass
```

## Discretion Recommendations

### Warning Tier Flag (Claude's Discretion)
**Recommendation:** Do NOT set `input_boolean.thermal_runaway_active` for warning tier.
**Rationale:** Warning tier (2-4F) is intentionally monitoring-only. Setting the flag would block TOU for a normal heating overshoot. The 2-4F range is common during active heating cycles. Only moderate (4-6F) and severe (>6F) should block TOU. [VERIFIED: D-01 specifies "small overshoots are normal during heating cycles"]

### Heater Detection Algorithm (Claude's Discretion)
**Recommendation:** Use simple threshold approach (>3.5kW) with `delay_on: 60s` and `delay_off: 120s`, NOT derivative-based detection.
**Rationale:** The Enphase integration updates every 60 seconds [CITED: https://www.home-assistant.io/integrations/enphase_envoy/]. At this update frequency, derivative-based detection would be noisy and unreliable -- you'd only get one data point per minute. A simple threshold with debounce via delay_on/delay_off is more robust. The hot tub heater draws approximately 4kW (as stated in phase description), so a 3.5kW threshold provides 500W margin. [ASSUMED: 4kW heater draw based on phase description; actual draw may vary]

### Enphase Integration Approach (Claude's Discretion)
**Recommendation:** Use HA's built-in Enphase Envoy integration (not REST sensor).
**Rationale:** The integration handles token authentication, firmware version differences, and entity management automatically. REST sensor would require manual token management. If the integration is not available (CT clamps not installed), create a stub template binary sensor that always reports `off` with a comment explaining how to wire it to the real sensor. [CITED: https://www.home-assistant.io/integrations/enphase_envoy/]

### Automation Structure (Claude's Discretion)
**Recommendation:** Single graduated file for thermal runaway (ha/thermal_runaway.yaml) with all three tiers. Separate file for auto-clear (ha/thermal_runaway_clear.yaml). Separate file for stale data (ha/stale_data.yaml).
**Rationale:** The three tiers share the same condition block (valid sensors + ESP32 online) and are mutually exclusive via `mode: single` + trigger ordering. Splitting into separate per-tier files would duplicate the condition block. The auto-clear is a distinct automation with its own trigger/condition/action. [VERIFIED: existing project uses one file per automation concern]

### Stale Data Grace Period (Claude's Discretion)
**Recommendation:** No grace period on the offline trigger. Immediate action on ESP32 disconnect.
**Rationale:** ESPHome already has built-in reconnection handling (WiFi reboot_timeout: 10min, API reboot_timeout: 15min) [VERIFIED: esphome/tublemetry.yaml lines 19, 39]. The status binary sensor only goes to "off" after the API connection is actually lost, which is already a delayed signal. Adding an additional grace period would leave a dangerous gap where automations act on stale data.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| All-or-nothing thermal runaway | Graduated 3-tier response | This phase | Prevents unnecessary floor drops on minor overshoots |
| No cross-automation coordination | input_boolean flag | This phase | Prevents TOU-runaway oscillation loop |
| Trust last-known sensor values | Gate on ESP32 online status | This phase | Prevents safety actions on stale data |
| Single heater status source (display bit) | Independent power validation | This phase | Catches discrepancies between display status and actual power draw |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Trigger ordering (severe first) ensures correct tier dispatch in mode: single | Architecture Patterns, Pattern 1 | If HA fires warning instead of severe, wrong response tier activates. Mitigation: test with live HA or use single trigger + computed tier in choose conditions |
| A2 | Enphase power consumption entity follows naming pattern sensor.envoy_{serial}_current_power_consumption | Architecture Patterns, Pattern 4 | Automation references wrong entity. Mitigation: D-13 stub fallback handles this; verify entity name against live HA |
| A3 | 4kW heater draw is the actual power consumption of the Balboa VS300FL4 heater | Discretion Recommendations | Threshold too high or too low for actual heater. Mitigation: configurable threshold value; user can adjust |
| A4 | ESPHome entity ID is binary_sensor.tublemetry_hot_tub_api_status (not tublemetry_hot_tub_status) | Common Pitfalls, Pitfall 5 | Wrong entity reference. Mitigation: verify against live HA entity registry |

## Open Questions

1. **Exact Enphase entity name**
   - What we know: The Enphase integration creates `sensor.envoy_*_current_power_consumption` with the serial number in the entity ID
   - What's unclear: The user's exact Enphase serial number and whether CT clamps are installed
   - Recommendation: Use placeholder in YAML, document that user must substitute their actual entity ID. The D-13 stub fallback covers the case where Enphase is unavailable.

2. **Trigger priority in mode: single with simultaneous template triggers**
   - What we know: HA `mode: single` prevents concurrent execution. Template triggers with `for:` durations fire when the condition has been continuously true for the specified time.
   - What's unclear: When multiple template triggers in the same automation all become true simultaneously (e.g., temp is 8F over, sustaining for 5 min), which trigger fires?
   - Recommendation: Use the single-trigger + computed-tier approach as a safer alternative if trigger ordering is unreliable. Test with the severe-first ordering initially.

3. **Whole-home baseline power**
   - What we know: The heater draws ~4kW, and detection is based on the absolute consumption level
   - What's unclear: What is the home's baseline power consumption? If baseline is 2kW and heater adds 4kW, threshold of 3.5kW would work. If baseline is 4kW, threshold needs to account for that.
   - Recommendation: Start with a high threshold (e.g., 5kW absolute) and let the user tune down based on observed data. Alternatively, use a template binary sensor that compares current consumption to a configurable baseline.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pytest | All tests | Yes | >=9.0.2 | -- |
| pyyaml | All tests | Yes | >=6.0 | -- |
| uv | Test runner | Yes | system | -- |
| Home Assistant | All automations | Yes (RPi4) | 2025.x+ | -- |
| ESPHome | ESP32 status sensor | Yes | 2024.x+ | -- |
| Enphase Envoy integration | PWR-01 | Unknown | -- | Stub binary sensor (D-13) |

**Missing dependencies with no fallback:**
- None -- all critical dependencies are available

**Missing dependencies with fallback:**
- Enphase Envoy integration: CT clamp installation unverified (per STATE.md blocker). Fallback is stub binary_sensor per D-13.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=9.0.2 with PyYAML >=6.0 |
| Config file | pyproject.toml [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/test_thermal_runaway.py tests/test_stale_data.py tests/test_heater_power.py -x` |
| Full suite command | `uv run pytest tests/ --ignore=tests/test_ladder_capture.py` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SAFE-01 | Graduated thermal runaway YAML has 3 trigger tiers, correct action structure, notification IDs | unit (YAML validation) | `uv run pytest tests/test_thermal_runaway.py -x` | Exists but must be REWRITTEN for graduated version |
| SAFE-02 | TOU automation has input_boolean condition; input_boolean helper exists in config | unit (YAML validation) | `uv run pytest tests/test_tou_automation.py -x` | NEW -- Wave 0 |
| SAFE-02 | Auto-clear automation references correct entities and conditions | unit (YAML validation) | `uv run pytest tests/test_thermal_runaway.py -x` (include auto-clear tests) | NEW tests in rewritten file |
| SAFE-03 | Stale data automation references correct status entity, correct actions | unit (YAML validation) | `uv run pytest tests/test_stale_data.py -x` | NEW -- Wave 0 |
| PWR-01 | Heater power binary sensor YAML valid, references Enphase entity or stub | unit (YAML validation) | `uv run pytest tests/test_heater_power.py -x` | NEW -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_thermal_runaway.py tests/test_stale_data.py -x`
- **Per wave merge:** `uv run pytest tests/ --ignore=tests/test_ladder_capture.py`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_thermal_runaway.py` -- EXISTS but needs complete rewrite for graduated version (current tests validate old 4-action structure)
- [ ] `tests/test_tou_automation.py` -- NEW, covers SAFE-02 oscillation prevention condition
- [ ] `tests/test_stale_data.py` -- NEW, covers SAFE-03 stale data gating
- [ ] `tests/test_heater_power.py` -- NEW, covers PWR-01 heater power binary sensor

## Security Domain

> Security enforcement is enabled (absent from config = enabled).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A -- local HA automations only |
| V3 Session Management | No | N/A |
| V4 Access Control | No | N/A -- HA handles entity access |
| V5 Input Validation | Yes | Safe float defaults (float(0), float(999)) prevent undefined behavior on invalid sensor values; unknown/unavailable gating in conditions |
| V6 Cryptography | No | N/A -- no secrets handled in automation YAML |

### Known Threat Patterns for HA Automation YAML

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Stale sensor data acted upon as current | Information Disclosure / Elevation | Gate all safety actions on ESP32 online status (SAFE-03) |
| Thermal runaway flag auto-cleared prematurely | Tampering | Separate auto-clear automation with independent sustain duration; severe tier requires manual clear only (D-08) |
| TOU raises setpoint during active runaway | Denial of Service (overheating) | input_boolean coordination flag checked as TOU condition (SAFE-02) |
| Enphase API unavailable, stub always-off | N/A (graceful degradation) | Stub binary sensor clearly documented; safety features (SAFE-01/02/03) independent of PWR-01 (D-14) |

## Sources

### Primary (HIGH confidence)
- `ha/thermal_runaway.yaml` -- Current automation structure, trigger pattern, action sequence [VERIFIED]
- `ha/tou_automation.yaml` -- Current TOU schedule, choose: pattern, entity references [VERIFIED]
- `ha/drift_detection.yaml` -- Condition gating pattern for unknown/unavailable [VERIFIED]
- `tests/test_drift_detection.py` -- YAML validation test pattern [VERIFIED]
- `tests/test_thermal_runaway.py` -- Existing runaway test structure (to be rewritten) [VERIFIED]
- `esphome/tublemetry.yaml` -- ESP32 binary_sensor status entity name and config [VERIFIED]
- [ESPHome Status Binary Sensor docs](https://esphome.io/components/binary_sensor/status/) -- Entity behavior on/off [CITED]
- [HA input_boolean docs](https://www.home-assistant.io/integrations/input_boolean/) -- Configuration and automation condition syntax [CITED]
- [HA Automation Trigger docs](https://www.home-assistant.io/docs/automation/trigger/) -- Template triggers, trigger IDs, choose: pattern [CITED]

### Secondary (MEDIUM confidence)
- [HA Enphase Envoy docs](https://www.home-assistant.io/integrations/enphase_envoy/) -- Power consumption entity naming, 60s update interval [CITED]
- [HA Threshold integration docs](https://www.home-assistant.io/integrations/threshold/) -- Binary sensor from numeric threshold [CITED]
- [HA Derivative integration docs](https://www.home-assistant.io/integrations/derivative/) -- Rate of change detection (evaluated, not recommended for this use case) [CITED]

### Tertiary (LOW confidence)
- Enphase entity naming pattern (`sensor.envoy_{serial}_current_power_consumption`) -- derived from docs, not verified against user's actual HA instance
- 4kW heater power draw -- stated in phase description, not independently verified

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all tools/libraries already in use in codebase, verified against actual files
- Architecture: HIGH -- patterns derived from existing codebase automations with verified HA documentation
- Pitfalls: HIGH -- identified from codebase analysis and HA documentation
- Enphase integration: MEDIUM -- documented but user's CT clamp availability unknown

**Research date:** 2026-04-12
**Valid until:** 2026-05-12 (stable domain -- HA automation YAML patterns change slowly)
