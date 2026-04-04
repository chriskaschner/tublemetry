---
estimated_steps: 74
estimated_files: 3
skills_used: []
---

# T02: Write Python mirror tests, update sensor.py codegen, add YAML sensor entry, and compile

Write tests/test_setpoint_detection.py mirroring the C++ state machine, wire the detected_setpoint sensor in sensor.py and tublemetry.yaml, then compile to verify end-to-end.

**Steps:**

1. Write `tests/test_setpoint_detection.py` with a Python `SetModeStateMachine` class that mirrors the C++ logic. Use `now_ms` parameter injection for deterministic timing (no real clock). Cover:
   - `TestSetModeEntry`: blank frame sets in_set_mode_; second blank without candidate does not publish setpoint; non-blank non-temperature does not set in_set_mode_
   - `TestSetModeTimeout`: temperature after SET_MODE_TIMEOUT_MS (2000) exits set mode and publishes normally; temperature before timeout suppresses publish
   - `TestSetpointPublish`: blank → temp (in set mode) → blank confirms and publishes setpoint; published value equals the candidate temp; same value not re-published
   - `TestTemperatureDiscrimination`: normal temperature (no prior blank) publishes immediately; temperature during set mode is suppressed; temperature after set-mode timeout publishes normally
   - `TestButtonInjectorFeed`: when setpoint is confirmed, set_known_setpoint() is called with the detected value (verify via mock/callback)
   - Target: ≥15 tests total

   The `SetModeStateMachine` class should accept `now_ms` on each `feed()` call:
   ```python
   SET_MODE_TIMEOUT_MS = 2000

   class SetModeStateMachine:
       def __init__(self):
           self.in_set_mode = False
           self.last_blank_seen_ms = 0
           self.set_temp_potential = float('nan')
           self.detected_setpoint = float('nan')
           self.published_setpoint = None  # last published setpoint value
           self.published_temperature = None  # last published temp value
           self.known_setpoint_fed = None  # value fed to injector

       def feed(self, display_str: str, now_ms: int = 0):
           """Returns ('temperature', value) | ('setpoint', value) | ('blank', None) | ('other', None)"""
           # mirror C++ classify_display_state_() set-mode logic
           stripped = display_str.replace(' ', '')
           if stripped == '':
               # blank branch
               self.in_set_mode = True
               self.last_blank_seen_ms = now_ms
               if not math.isnan(self.set_temp_potential):
                   if math.isnan(self.detected_setpoint) or self.set_temp_potential != self.detected_setpoint:
                       self.detected_setpoint = self.set_temp_potential
                       self.published_setpoint = self.detected_setpoint
                       self.known_setpoint_fed = self.detected_setpoint
               self.set_temp_potential = float('nan')
               return ('blank', None)
           is_numeric = len(stripped) >= 2 and stripped.isdigit()
           if is_numeric:
               temp = float(stripped)
               if self.in_set_mode and (now_ms - self.last_blank_seen_ms) >= SET_MODE_TIMEOUT_MS:
                   self.in_set_mode = False
                   self.set_temp_potential = float('nan')
               if self.in_set_mode:
                   self.set_temp_potential = temp
                   return ('suppressed', temp)
               else:
                   self.published_temperature = temp
                   return ('temperature', temp)
           return ('other', None)
   ```

2. Add to `sensor.py`:
   - Import: `CONF_DETECTED_SETPOINT = "detected_setpoint"` at top of file (alongside CONF_TEMPERATURE)
   - Schema entry:
     ```python
     cv.Optional(CONF_DETECTED_SETPOINT): sensor.sensor_schema(
         icon="mdi:thermometer",
         accuracy_decimals=0,
         state_class=STATE_CLASS_MEASUREMENT,
     ),
     ```
   - `to_code()` entry:
     ```python
     if conf := config.get(CONF_DETECTED_SETPOINT):
         sens = await sensor.new_sensor(conf)
         cg.add(parent.set_detected_setpoint_sensor(sens))
     ```

3. Add to `esphome/tublemetry.yaml` under the `sensor > tublemetry_display` block (after `temperature:`):
   ```yaml
   detected_setpoint:
     name: "Hot Tub Detected Setpoint"
   ```

4. Run `uv run pytest tests/ --ignore=tests/test_ladder_capture.py -q` — must show 274 + new tests, all pass.

5. Compile: `.venv/bin/esphome compile esphome/tublemetry.yaml` — must show [SUCCESS].

**Note on YAML compile environment**: ESPHome in this worktree requires `secrets.yaml` to be symlinked. Check if it already exists: `ls esphome/secrets.yaml`. If not: `ln -s ../../secrets.yaml esphome/secrets.yaml`. Use `.venv/bin/esphome` directly, not `uv run esphome`.

## Inputs

- ``esphome/components/tublemetry_display/tublemetry_display.h` — set_detected_setpoint_sensor() setter from T01`
- ``esphome/components/tublemetry_display/tublemetry_display.cpp` — state machine logic from T01 (for Python mirroring)`
- ``esphome/components/tublemetry_display/sensor.py` — existing sensor platform to extend`
- ``esphome/tublemetry.yaml` — existing YAML to extend with new sensor entry`

## Expected Output

- ``tests/test_setpoint_detection.py` — new: ≥15 tests across SetModeStateMachine mirror classes`
- ``esphome/components/tublemetry_display/sensor.py` — CONF_DETECTED_SETPOINT added to schema and to_code()`
- ``esphome/tublemetry.yaml` — detected_setpoint sensor entry added under tublemetry_display sensor block`

## Verification

uv run pytest tests/ --ignore=tests/test_ladder_capture.py -q 2>&1 | tail -3 && echo '---' && .venv/bin/esphome compile esphome/tublemetry.yaml 2>&1 | grep -E 'SUCCESS|ERROR|error:'

## Observability Impact

test_setpoint_detection.py provides regression coverage for all set-mode state transitions, ensuring future changes don't silently break temperature discrimination.
