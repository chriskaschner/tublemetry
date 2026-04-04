---
estimated_steps: 73
estimated_files: 3
skills_used: []
---

# T01: Implement setpoint detection state machine in C++ and add ButtonInjector setter

Add the set-mode state machine to classify_display_state_() and wire the detected-setpoint sensor and ButtonInjector feedback.

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

## Inputs

- ``esphome/components/tublemetry_display/tublemetry_display.h` — add new members and setter`
- ``esphome/components/tublemetry_display/tublemetry_display.cpp` — modify classify_display_state_()`
- ``esphome/components/tublemetry_display/button_injector.h` — add set_known_setpoint() public method`

## Expected Output

- ``esphome/components/tublemetry_display/tublemetry_display.h` — SET_MODE_TIMEOUT_MS, in_set_mode_, last_blank_seen_ms_, set_temp_potential_, detected_setpoint_, detected_setpoint_sensor_ added; set_detected_setpoint_sensor() setter added`
- ``esphome/components/tublemetry_display/tublemetry_display.cpp` — classify_display_state_() modified with set-mode state machine; #include <cmath> added`
- ``esphome/components/tublemetry_display/button_injector.h` — set_known_setpoint() public method added`

## Verification

uv run pytest tests/ --ignore=tests/test_ladder_capture.py -q 2>&1 | tail -3

## Observability Impact

ESP_LOGI: 'Setpoint detected: %.0fF' on each setpoint publish. ESP_LOGD: set-mode entry on blank, candidate capture on suppressed temp, timeout on set-mode expiry. All transitions visible at DEBUG level; detection events at INFO.
