# S02: Setpoint Detection + Temperature Discrimination — Research

**Date:** 2026-04-04
**Slice:** M002/S02
**Requirements owned:** R003, R004, R009

## Summary

S02 adds a setpoint detection state machine to `process_frame_()` and wires a new detected-setpoint sensor into the ESPHome codegen layer. The VS300FL4 signals setpoint display mode by alternating between blank frames (`0x00/0x00/0x00`) and temperature-value frames. kgstorm's algorithm detects this pattern by tracking blank stability and a last-seen candidate temperature. When blanks are stable and a candidate temperature was seen within the last 3 seconds, the setpoint is published and the temperature sensor is suppressed for that reading.

The core algorithm is well understood — kgstorm's `esp32-spa.h` was fully read. The key difference from kgstorm's implementation is that Tublemetry's stability filter already runs before this logic: by the time we're routing values at the `classify_display_state_()` level, the stability filter has already enforced 3 consecutive identical frames. This simplifies the setpoint logic somewhat — blank stability is already established by the existing `stable_count_` / `candidate_display_string_` machinery.

The R009 integration (feed known setpoint to ButtonInjector) is a one-liner in `process_frame_()` after setpoint detection: call `injector_->set_known_setpoint(detected_setpoint_)`. The PROBING phase in `button_injector.cpp` needs no structural change — the existing `known_setpoint_` field is already the bypass mechanism.

This is high-risk because the setpoint detection state machine touches the temperature publish path (R003) — a logic error here pollutes temperature history instead of preventing it. The state machine must be precise.

## Recommendation

Adapt kgstorm's algorithm to Tublemetry's architecture. The natural fit is:

1. **Add set-mode tracking members** to `TublemetryDisplay` (boolean `in_set_mode_`, timestamps, `detected_setpoint_`).
2. **Add a detected-setpoint sensor pointer** to `TublemetryDisplay` and wire it via a new `binary_sensor.py`-style platform file (`sensor.py` already has room but setpoint is a `sensor::Sensor`, not binary).
3. **Modify `classify_display_state_()`** to run setpoint detection logic: detect blank→temp→blank alternation pattern, suppress temperature publish when in set mode, publish setpoint when pattern confirms it.
4. **Add `set_known_setpoint()` to ButtonInjector** (or expose `known_setpoint_` directly) and call it from `process_frame_()` when setpoint is detected.
5. **New Python platform file `binary_sensor.py`** for S03's heater/pump/light — not needed in S02. The setpoint is a `sensor::Sensor`, so it goes into the existing `sensor.py`.
6. **Write `tests/test_setpoint_detection.py`** mirroring the state machine in Python.

**Key simplification:** Tublemetry's `classify_display_state_()` already sees post-stability-filter display strings. In kgstorm's code, setpoint detection interacts directly with per-frame candidate tracking. Here, by the time `classify_display_state_()` runs, the display string is already stable (3 frames confirmed). So "blank stability" is just: did we see `"   "` (the stable blank) arrive after `classify_display_state_()` classified it as "blank"? Yes — we track `in_set_mode_` via a timestamp: when a blank is seen, record `last_blank_ms_`. When a temperature is seen while `in_set_mode_`, record it as `set_temp_potential_`. When blank is seen again and potential is set, publish setpoint.

**SET_MODE_TIMEOUT_MS = 2000ms** (kgstorm's value — start here, tune after live observation).

## Implementation Landscape

### Key Files

- `esphome/components/tublemetry_display/tublemetry_display.h` — Add 4 new protected members: `in_set_mode_` (bool), `last_blank_seen_ms_` (uint32_t), `set_temp_potential_` (float, NAN=none), `detected_setpoint_` (float, NAN=none), `detected_setpoint_sensor_` (sensor::Sensor*). Add `set_detected_setpoint_sensor()` setter. Add `SET_MODE_TIMEOUT_MS` constexpr.
- `esphome/components/tublemetry_display/tublemetry_display.cpp` — Modify `classify_display_state_()`: blank branch sets `in_set_mode_=true` and records `last_blank_seen_ms_`; temperature branch: if `in_set_mode_`, save candidate but skip temperature publish; non-blank-non-temp: check timeout. After stability, when blank is seen again and potential is set, publish setpoint. Also call `injector_->set_known_setpoint(detected_setpoint_)` when setpoint detected.
- `esphome/components/tublemetry_display/button_injector.h` — Add `set_known_setpoint(float sp)` public method that sets `known_setpoint_` directly. (Or just make `known_setpoint_` accessible via a setter.)
- `esphome/components/tublemetry_display/sensor.py` — Add `CONF_DETECTED_SETPOINT = "detected_setpoint"` and a sensor schema entry for it. Wire `set_detected_setpoint_sensor()` call in `to_code()`.
- `esphome/tublemetry.yaml` — Add `detected_setpoint:` entry under `sensor > tublemetry_display` block. New entity name: `"Hot Tub Detected Setpoint"` (→ entity_id `sensor.tublemetry_hot_tub_detected_setpoint`).
- `tests/test_setpoint_detection.py` — New: Python mirror of the set-mode state machine, 15-20 tests. Classes: TestSetModeEntry, TestSetModeExit, TestSetpointPublish, TestTemperatureDiscrimination, TestButtonInjectorIntegration.

### Set Mode State Machine (precise algorithm for C++)

```
// In classify_display_state_(), after display_str is classified:

// When blank arrives:
if (state == "blank") {
    in_set_mode_ = true;
    last_blank_seen_ms_ = millis();
    // If we have a potential, this is the confirmation blank — publish setpoint
    if (!std::isnan(set_temp_potential_) && set_temp_potential_ != detected_setpoint_) {
        detected_setpoint_ = set_temp_potential_;
        if (detected_setpoint_sensor_) detected_setpoint_sensor_->publish_state(detected_setpoint_);
        // Feed to button injector
        if (injector_) injector_->set_known_setpoint(detected_setpoint_);
        ESP_LOGI(TAG, "Setpoint detected: %.0fF", detected_setpoint_);
    }
    set_temp_potential_ = NAN; // reset for next cycle
    // Do NOT publish temperature sensor
    return;  // early return, skip temperature publish
}

// When temperature arrives:
if (state == "temperature") {
    // Check if set mode timed out
    if (in_set_mode_ && (millis() - last_blank_seen_ms_) >= SET_MODE_TIMEOUT_MS) {
        in_set_mode_ = false;
        set_temp_potential_ = NAN;
        ESP_LOGD(TAG, "Set mode timeout — returning to normal");
    }
    if (in_set_mode_) {
        // This is a setpoint flash — record candidate, suppress temperature publish
        set_temp_potential_ = temp_value;
        ESP_LOGD(TAG, "Set mode temp candidate: %.0fF (suppressing temperature publish)", temp_value);
        // Do NOT publish temperature_sensor_
        return;  // or continue without publishing
    }
    // Normal temperature — publish as usual
    temperature_sensor_->publish_state(temp_value);
}
```

Note: the `classify_display_state_()` function currently calls `temperature_sensor_->publish_state()` directly. The setpoint detection must run here, not in `process_frame_()`, because this is where the state classification happens. The function currently has a void return with no early exit — the setpoint discrimination logic needs to restructure it slightly to skip the temperature publish path when in set mode.

### ButtonInjector change

Add to `button_injector.h`:
```cpp
void set_known_setpoint(float sp) { this->known_setpoint_ = sp; }
```

This is a 1-line change. `known_setpoint_` is already used by `request_temperature()` to skip PROBING.

### Sensor.py change

Add `CONF_DETECTED_SETPOINT = "detected_setpoint"` and:
```python
cv.Optional(CONF_DETECTED_SETPOINT): sensor.sensor_schema(
    icon="mdi:thermometer",
    accuracy_decimals=0,
    state_class=STATE_CLASS_MEASUREMENT,
),
```
And in `to_code()`:
```python
if conf := config.get(CONF_DETECTED_SETPOINT):
    sens = await sensor.new_sensor(conf)
    cg.add(parent.set_detected_setpoint_sensor(sens))
```

### YAML change

Add under `sensor > tublemetry_display`:
```yaml
detected_setpoint:
  name: "Hot Tub Detected Setpoint"
```

### Build Order

1. **C++ changes first** (`.h` and `.cpp`) — the state machine is the risk; get it right and testable before touching Python codegen.
2. **Python mirror tests** — `test_setpoint_detection.py` mirrors the state machine. Write these before or in parallel with the C++ implementation.
3. **Python codegen** (`sensor.py`) — straightforward after C++ is settled.
4. **YAML** — add the new sensor entity.
5. **Compile** — verify the new `detected_setpoint_sensor_` pointer chain works end-to-end.

### Verification Approach

- `uv run pytest tests/ --ignore=tests/test_ladder_capture.py` → 274 + new setpoint tests, all pass.
- `.venv/bin/esphome compile esphome/tublemetry.yaml` → [SUCCESS].
- Live behavior (post-OTA): press WARM on the panel, observe `in_set_mode_` debug logs showing blank/temp alternation; `sensor.tublemetry_hot_tub_detected_setpoint` updates; `sensor.tublemetry_hot_tub_temperature` shows no spike.

## Constraints

- `classify_display_state_()` is called from `loop()` context (not ISR) — `millis()` calls are safe here.
- `NAN` requires `<cmath>` — already included transitively via button_injector.cpp; verify it's included in tublemetry_display.cpp. If not, add it.
- `detected_setpoint_` initial value should be `NAN` (float member with `{NAN}` initializer in header), same pattern as `known_setpoint_` in ButtonInjector.
- Entity ID for new sensor must follow `sensor.tublemetry_hot_tub_<name>` — name `"Hot Tub Detected Setpoint"` → `sensor.tublemetry_hot_tub_detected_setpoint`. This is a new ID, not replacing any existing one (R012 preserved).
- `SET_MODE_TIMEOUT_MS` should be a `constexpr` in the class, initialized to `2000`. May need tuning after live observation but 2000ms matches kgstorm.

## Common Pitfalls

- **Publishing temperature inside set mode** — the early-return-on-blank and suppress-on-temp-while-in-set-mode logic must be airtight. A missed early return pollutes the temperature sensor.
- **set_temp_potential_ not reset on set mode exit** — if `set_mode_timeout` fires without a confirming blank, `set_temp_potential_` must be reset. Otherwise a stale candidate from a previous set mode cycle gets published on the next blank.
- **classify_display_state_() is currently void with no early exits** — adding early returns requires re-checking that the `if (changed) publish_timestamp_()` call at the end of `process_frame_()` is still correct. Since `classify_display_state_()` doesn't affect `changed`, this is safe — just be careful to exit the function (return) not exit process_frame_.
- **`std::isnan` requires `<cmath>`** — used in button_injector.cpp already, but tublemetry_display.cpp doesn't currently include it. Will need `#include <cmath>` added.
- **Test mirroring**: the Python test state machine should use wall-clock time injection (pass `now_ms` as a parameter) rather than `time.time()`, to make tests deterministic. Mirror the C++ logic with a `SetModeStateMachine` Python class that accepts `now_ms`.

## Open Risks

- **VS300FL4 SET_MODE_TIMEOUT_MS**: kgstorm uses 2000ms. If the VS300FL4 alternates at a different rate, the timeout may be too short or too long. Start with 2000ms and log all set-mode transitions at INFO level so timing can be tuned from logs without re-flashing.
- **Blank frames in normal mode**: The tub's display goes genuinely blank during non-set-mode transitions (e.g., startup, economy mode entry). Need to confirm these don't trigger spurious set-mode entry. The timeout handles this: if no candidate temp arrives within 2s of the blank, set mode exits cleanly. The test suite should include a "single blank without temp candidate" test case.
