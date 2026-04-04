# S02: Setpoint Detection + Temperature Discrimination

**Goal:** Add setpoint detection state machine to classify_display_state_() that identifies blank-frame alternation, suppresses temperature publishes during set mode, publishes a dedicated detected-setpoint sensor, and feeds the known setpoint to ButtonInjector so PROBING phase is skipped.
**Demo:** After this: After this: HA shows a separate detected-setpoint sensor that tracks the controller's actual setpoint. Temperature sensor no longer publishes setpoint flashes. Button injector uses display-detected setpoint instead of PROBING phase.

## Tasks
- [x] **T01: Added set-mode state machine to classify_display_state_() with blank-frame detection, temperature suppression, setpoint confirmation, and ButtonInjector feedback; 274 existing tests pass** — Add the set-mode state machine to classify_display_state_() and wire the detected-setpoint sensor and ButtonInjector feedback.

This is the high-risk task — the state machine touches the temperature publish path (R003). A logic error here causes setpoint flashes to pollute temperature history instead of being routed to the setpoint sensor.

**Steps:**

1. Add `#include <cmath>` to `tublemetry_display.cpp` (needed for `std::isnan`).

2. In `tublemetry_display.h`, add to the protected section:
   ```cpp
   // Setpoint detection state machine
   static constexpr uint32_t SET_MODE_TIMEOUT_MS = 2000;
   bool in_set_mode_{false};
   uint32_t last_blank_seen_ms_{0};
   float set_temp_potential_{NAN};
   float detected_setpoint_{NAN};
   sensor::Sensor *detected_setpoint_sensor_{nullptr};
   ```
   Add public setter: `void set_detected_setpoint_sensor(sensor::Sensor *s) { this->detected_setpoint_sensor_ = s; }`

3. In `button_injector.h`, add public method:
   ```cpp
   void set_known_setpoint(float sp) { this->known_setpoint_ = sp; }
   ```

4. Modify `classify_display_state_()` in `tublemetry_display.cpp`. The current structure: strips display_str, classifies state, publishes temperature if is_numeric, publishes display_state_sensor_ on change. Restructure the `is_numeric` and blank branches:

   **Blank branch** (replace `} else if (stripped.empty()) { state = "blank"; }`):
   ```cpp
   } else if (stripped.empty()) {
     state = "blank";
     in_set_mode_ = true;
     last_blank_seen_ms_ = millis();
     // Confirmation blank: if we have a candidate, publish setpoint
     if (!std::isnan(set_temp_potential_)) {
       if (std::isnan(detected_setpoint_) || set_temp_potential_ != detected_setpoint_) {
         detected_setpoint_ = set_temp_potential_;
         if (detected_setpoint_sensor_ != nullptr)
           detected_setpoint_sensor_->publish_state(detected_setpoint_);
         if (injector_ != nullptr)
           injector_->set_known_setpoint(detected_setpoint_);
         ESP_LOGI(TAG, "Setpoint detected: %.0fF", detected_setpoint_);
       }
     }
     set_temp_potential_ = NAN;
     // Skip temperature publish — already handled above; fall through to state publish
   ```

   **Temperature branch** (after `if (is_numeric) {` and before `injector_->feed_display_temperature`):
   ```cpp
   if (is_numeric) {
     state = "temperature";
     float temp = static_cast<float>(atoi(stripped.c_str()));
     // Check set mode timeout
     if (in_set_mode_ && (millis() - last_blank_seen_ms_) >= SET_MODE_TIMEOUT_MS) {
       in_set_mode_ = false;
       set_temp_potential_ = NAN;
       ESP_LOGD(TAG, "Set mode timeout — returning to normal");
     }
     if (in_set_mode_) {
       // Setpoint flash — record candidate, suppress temperature publish
       set_temp_potential_ = temp;
       ESP_LOGD(TAG, "Set mode candidate: %.0fF (suppressing temperature publish)", temp);
       // Still feed to injector for PROBING/VERIFYING phases
       if (injector_ != nullptr)
         injector_->feed_display_temperature(temp);
       // Do NOT publish temperature_sensor_ — early return from classify, after state tracking
     } else {
       // Normal temperature
       if (injector_ != nullptr)
         injector_->feed_display_temperature(temp);
       if (temperature_sensor_ != nullptr)
         temperature_sensor_->publish_state(temp);
     }
   ```
   After the closing `}` of the `is_numeric` block, add a return for the suppressed case. The cleanest approach: restructure so the state-sensor publish and return happen correctly. Use a `bool suppress_temp = in_set_mode_` flag captured before the temperature branch executes, then skip the publish but not the state update.

   **Concrete restructure**: Use a local `bool suppress_publish = false;` at the top of classify_display_state_(). Set it to `true` in the blank branch (after set_temp_potential_ reset) and in the temperature-while-in-set-mode branch. At the bottom, guard temperature publish with `if (!suppress_publish)`. This avoids early returns and keeps the display_state_sensor_ publish path intact.

   Actually simpler: keep the existing structure, but:
   - In the blank branch: set `in_set_mode_=true`, record `last_blank_seen_ms_`, check for confirmation, reset candidate. Then NOT publish temperature (blank has no temperature to publish anyway — currently just sets state="blank" without any publish). No change needed here.
   - In the is_numeric branch: add the set-mode check BEFORE calling temperature_sensor_->publish_state(). If `in_set_mode_` and not timed out, store candidate and skip the publish_state call. The `state` variable still gets set to "temperature" and the display_state_sensor_ still publishes "temperature" — that's acceptable (display_state reflects what's on display, not whether we suppressed the sensor).

5. Verify with `uv run pytest tests/test_setpoint_detection.py` (written in T02 — but build check: `uv run pytest tests/ --ignore=tests/test_ladder_capture.py` should still pass 274/274 after C++ changes since no Python tests change here).
  - Estimate: 1.5h
  - Files: esphome/components/tublemetry_display/tublemetry_display.h, esphome/components/tublemetry_display/tublemetry_display.cpp, esphome/components/tublemetry_display/button_injector.h
  - Verify: uv run pytest tests/ --ignore=tests/test_ladder_capture.py -q 2>&1 | tail -3
- [x] **T02: Added 25 setpoint-detection tests, wired detected_setpoint in sensor.py and tublemetry.yaml, compiled successfully (299/299 tests pass, [SUCCESS])** — Write tests/test_setpoint_detection.py mirroring the C++ state machine, wire the detected_setpoint sensor in sensor.py and tublemetry.yaml, then compile to verify end-to-end.

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
  - Estimate: 1.5h
  - Files: tests/test_setpoint_detection.py, esphome/components/tublemetry_display/sensor.py, esphome/tublemetry.yaml
  - Verify: uv run pytest tests/ --ignore=tests/test_ladder_capture.py -q 2>&1 | tail -3 && echo '---' && .venv/bin/esphome compile esphome/tublemetry.yaml 2>&1 | grep -E 'SUCCESS|ERROR|error:'
