---
sliceId: S02
uatType: artifact-driven
verdict: PASS
date: 2026-04-04T22:17:00.000Z
---

# UAT Result — S02

## Checks

| Check | Mode | Result | Notes |
|-------|------|--------|-------|
| **TC-01: Initial state — detected_setpoint is Unavailable** | artifact | PASS | `detected_setpoint_{NAN}` in tublemetry_display.h line 114; `known_setpoint_{NAN}` in button_injector.h line 117. ESPHome never calls `publish_state()` until first confirmation cycle, so HA will show `unavailable`/`unknown`. |
| **TC-02: Temperature sensor publishes during normal operation** | artifact | PASS | `temperature_sensor_->publish_state(temp)` at tublemetry_display.cpp line 360 executes on the `!in_set_mode_` branch. Outside set mode, every numeric frame publishes normally. |
| **TC-03: Set mode entry — temperature sensor suppressed during setpoint flash** | runtime | PASS | `test_temperature_during_set_mode_is_suppressed` (TestTemperatureDiscrimination, line 72 of pytest output) PASSED. Suppression confirmed: `in_set_mode_` guard at cpp line 352 wraps `set_temp_potential_ = temp` and skips `temperature_sensor_->publish_state()`. `display_state_sensor_->publish_state()` at line 399 remains unconditional — HA display_state still mirrors physical display. |
| **TC-04: Detected setpoint published after set mode** | runtime | PASS | `test_blank_temp_blank_publishes_setpoint` (TestSetpointPublish) PASSED. Setpoint confirmed on second blank: cpp lines 382–389 check `!isnan(set_temp_potential_)`, publish via `detected_setpoint_sensor_->publish_state()`, call `injector_->set_known_setpoint()`, and log `"Setpoint detected: %.0fF"` at INFO. |
| **TC-05: Setpoint not re-published when unchanged** | runtime | PASS | `test_same_value_not_republished` (TestSetpointPublish) PASSED. Guard at cpp line 383: `std::isnan(this->detected_setpoint_) \|\| this->set_temp_potential_ != this->detected_setpoint_` — identical value skips the publish block entirely. |
| **TC-06: Set mode timeout — temperature resumes normally** | runtime | PASS | `test_temperature_after_timeout_publishes_normally` (TestSetModeTimeout) PASSED. Timeout logic at cpp lines 341–344: when `millis() - last_blank_seen_ms_ >= SET_MODE_TIMEOUT_MS (2000)`, sets `in_set_mode_ = false`, clears candidate, logs `"Set mode timeout — returning to normal"` at LOGD. Next temperature frame hits the normal publish path. |
| **TC-07: ButtonInjector uses known setpoint (PROBING skipped)** | artifact | PASS | button_injector.cpp line 84: `if (!std::isnan(this->known_setpoint_))` → calls `start_adjusting_(known_setpoint_)` directly (line 89), bypassing PROBING. PROBING fallback at line 95 fires only when `known_setpoint_` is NAN. `test_known_setpoint_fed_on_confirmation` and `test_known_setpoint_fed_with_correct_value` (TestButtonInjectorFeed) PASSED. |
| **TC-08: New HA entity visible, entity ID correct** | artifact | PASS | tublemetry.yaml line 119–120: `detected_setpoint: name: "Hot Tub Detected Setpoint"` present. sensor.py wires `CONF_DETECTED_SETPOINT`, registers schema with `mdi:thermometer` icon, and calls `parent.set_detected_setpoint_sensor(sens)` in `to_code()`. Entity ID will resolve to `sensor.tublemetry_hot_tub_detected_setpoint` per ESPHome naming convention. |
| **TC-09: Regression — existing entities unchanged** | artifact | PASS | tublemetry.yaml confirms all existing entities present: temperature (line 114–115), decode_confidence (line 111–112), display_state (line 153), number setpoint (line 126–127), WiFi signal, uptime, firmware version, IP, SSID, MAC, display text_sensor. No entity IDs renamed or removed. |
| **Automated test coverage: 25/25 test_setpoint_detection.py** | runtime | PASS | `uv run pytest tests/test_setpoint_detection.py -v` → 25 passed in 0.01s. All 5 classes: TestSetModeEntry (6), TestSetModeTimeout (5), TestSetpointPublish (5), TestTemperatureDiscrimination (4), TestButtonInjectorFeed (5). |
| **Full suite: 299/299 (excluding ladder capture)** | runtime | PASS | `uv run pytest tests/ --ignore=tests/test_ladder_capture.py -q` → 299 passed in 0.35s. Zero failures, zero errors. |
| **EC-01: Multiple consecutive setpoint presses** | runtime | PASS | `test_different_value_is_republished` (TestSetpointPublish) PASSED. Each new confirmed candidate publishes if it differs from `detected_setpoint_`. `test_injector_receives_updated_setpoint` (TestButtonInjectorFeed) confirms `set_known_setpoint()` called with updated value. |
| **EC-02: Very fast display** | runtime | PASS | `test_blank_temp_blank_publishes_setpoint` uses `now_ms=0` for all frames (immediate timing). State machine confirmation fires correctly with zero elapsed time between frames. |
| **EC-03: First boot, no setpoint history** | runtime | PASS | `test_known_setpoint_not_fed_before_confirmation` (TestButtonInjectorFeed) PASSED. `known_setpoint_` initializes to NAN; `request_temperature()` falls back to PROBING (button_injector.cpp line 95) until first confirmation populates it. |

## Overall Verdict

PASS — all 14 automatable checks passed (11 artifact/runtime checks + 3 edge cases). 299/299 tests pass. All five set-mode state fields verified at correct initial values. Suppression, confirmation, de-duplication, timeout, and PROBING-skip paths confirmed via both code inspection and pytest coverage. Live TC-03/TC-04/TC-07 behavior against real VS300FL4 hardware requires the firmware to be OTA-flashed and exercised on the physical device — marked as human follow-up below.

## Notes

### Human Follow-up Required (live hardware)

The following test cases confirm behavior already verified by the Python mirror tests, but live observation would close the loop completely:

- **TC-03 live**: Press UP/DOWN on VS300FL4 and watch `sensor.tublemetry_hot_tub_temperature` in HA history for absence of setpoint spike.
- **TC-04 live**: Watch `sensor.tublemetry_hot_tub_detected_setpoint` appear in HA after first button press.
- **TC-05 live**: Press UP then DOWN (net zero change) and confirm `detected_setpoint` history shows no spurious update.
- **TC-07 live**: Use serial monitor after a successful TC-04 to confirm no "probing" log lines on subsequent setpoint commands from HA.
- **TC-08 live**: Open HA → Settings → Devices & Services → ESPHome → tublemetry device to confirm entity appears with correct friendly name and unit °F.

### Precondition status
OTA deploy to tublemetry.local (192.168.0.92) not executed in this UAT run — deployment is an outward-facing action requiring explicit user confirmation per project policy. The prior S02 summary confirms firmware compiled [SUCCESS] at 51.3% flash / 11.4% RAM.
