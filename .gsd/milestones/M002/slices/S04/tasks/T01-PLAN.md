---
estimated_steps: 83
estimated_files: 5
skills_used: []
---

# T01: Add REFRESHING phase to ButtonInjector and wire auto-refresh timer in TublemetryDisplay

Implement the auto-refresh keepalive. Four files change in concert; tests follow the existing Python mirror pattern from test_setpoint_detection.py and test_button_injection.py.

**C++ changes — button_injector.h:**
1. Add `REFRESHING` to `InjectorPhase` enum (after `TEST_PRESS`).
2. Add public method `void refresh()` — rejects if busy, transitions to REFRESHING. Does NOT touch `known_setpoint_`.
3. Add private method declaration `void loop_refreshing_()` at the bottom of the protected section.

**C++ changes — button_injector.cpp:**
4. Add `case InjectorPhase::REFRESHING: return "refreshing";` to `phase_to_string()`.
5. Add `refresh()` implementation: reject if not configured or busy (same guards as `request_temperature()`). Log at INFO. Transition to REFRESHING.
6. Add `case InjectorPhase::REFRESHING: this->loop_refreshing_(); break;` to the `switch` in `loop()`.
7. Add `loop_refreshing_()` implementation. This phase fires a down press, then an up press (net zero), then transitions to COOLDOWN. Structure: two sub-phases tracked by a bool or by reusing `presses_remaining_` (set 2 on entry via `refresh()`). Simplest: set `presses_remaining_ = 2` and `adjusting_up_ = false` in `refresh()`, then in `loop_refreshing_()` mirror `loop_adjusting_()` but alternate direction: first press down (presses_remaining_ == 2), second press up (presses_remaining_ == 1). When presses_remaining_ reaches 0, transition to COOLDOWN. Key invariant: `known_setpoint_` must NOT be modified anywhere in `refresh()` or `loop_refreshing_()`.

**C++ changes — tublemetry_display.h:**
8. Add `static constexpr uint32_t SET_FORCE_INTERVAL_MS = 300000;` to the constants block (after `SET_MODE_TIMEOUT_MS`).
9. Add `uint32_t last_setpoint_capture_ms_{0};` to the setpoint detection state machine fields block.

**C++ changes — tublemetry_display.cpp:**
10. In `classify_display_state_()`, inside the blank-branch confirmation block (where `set_known_setpoint()` is called), add `this->last_setpoint_capture_ms_ = millis();` immediately after the `ESP_LOGI` for setpoint detection.
11. In `loop()`, after `this->injector_->loop()`, add the auto-refresh guard:
```cpp
if (this->injector_ != nullptr && this->injector_->is_configured() && !this->injector_->is_busy()) {
    bool needs_refresh = std::isnan(this->detected_setpoint_) ||
        (this->last_setpoint_capture_ms_ > 0 &&
         millis() - this->last_setpoint_capture_ms_ >= SET_FORCE_INTERVAL_MS);
    if (needs_refresh) {
        if (std::isnan(this->detected_setpoint_)) {
            ESP_LOGI(TAG, "Auto-refresh: no setpoint yet — triggering initial COOL press");
        } else {
            ESP_LOGI(TAG, "Auto-refresh: triggering COOL press (setpoint cache age: %lums)",
                     (unsigned long)(millis() - this->last_setpoint_capture_ms_));
        }
        this->injector_->refresh();
    }
}
```

**Tests — tests/test_auto_refresh.py (new file):**
12. Create `tests/test_auto_refresh.py` with two test classes.

`TestRefreshPhase` (mirrors ButtonInjector refresh behavior):
- `test_refresh_fires_down_then_up`: mock-injector call sequence is [down, up] — verify both presses fire
- `test_refresh_does_not_clear_known_setpoint`: after refresh(), known_setpoint is unchanged
- `test_refresh_rejected_when_busy`: calling refresh() while busy is a no-op
- `test_refresh_rejected_when_not_configured`: calling refresh() with no pins is a no-op

Use a `RefreshStateMachine` Python class that mirrors the REFRESHING phase:
```python
class RefreshStateMachine:
    def __init__(self, known_setpoint=float('nan')):
        self.known_setpoint = known_setpoint
        self.busy = False
        self.press_log = []  # list of 'down' or 'up'

    def refresh(self):
        if self.busy:
            return False
        self.busy = True
        # Simulate two presses: down then up
        self.press_log.append('down')
        self.press_log.append('up')
        self.busy = False
        return True
```

`TestAutoRefresh` (mirrors TublemetryDisplay loop() auto-refresh trigger):
- `test_refresh_triggered_on_nan_setpoint`: with detected_setpoint=NaN, needs_refresh=True
- `test_refresh_triggered_after_interval`: with last_capture=100ms, now=300100ms (300s elapsed), needs_refresh=True
- `test_refresh_not_triggered_before_interval`: with last_capture=100ms, now=200000ms (200s elapsed), needs_refresh=False
- `test_refresh_not_triggered_when_busy`: injector busy, needs_refresh=True but refresh() not called
- `test_refresh_not_triggered_when_capture_ms_zero_and_setpoint_known`: last_capture=0 with known setpoint — needs_refresh=False (avoids spurious refires after fresh detection on same boot)
- `test_last_capture_updated_on_setpoint_confirmation`: feed blank→temp→blank, verify last_setpoint_capture_ms is updated

For the TestAutoRefresh interval checks, use a `AutoRefreshController` Python class:
```python
SET_FORCE_INTERVAL_MS = 300_000

class AutoRefreshController:
    def __init__(self):
        self.detected_setpoint = float('nan')
        self.last_setpoint_capture_ms = 0
        self.refresh_calls = 0

    def on_setpoint_confirmed(self, value, now_ms):
        self.detected_setpoint = value
        self.last_setpoint_capture_ms = now_ms

    def tick(self, now_ms, injector_busy=False):
        needs_refresh = (
            math.isnan(self.detected_setpoint) or
            (self.last_setpoint_capture_ms > 0 and
             now_ms - self.last_setpoint_capture_ms >= SET_FORCE_INTERVAL_MS)
        )
        if needs_refresh and not injector_busy:
            self.refresh_calls += 1
```

## Inputs

- `esphome/components/tublemetry_display/button_injector.h`
- `esphome/components/tublemetry_display/button_injector.cpp`
- `esphome/components/tublemetry_display/tublemetry_display.h`
- `esphome/components/tublemetry_display/tublemetry_display.cpp`
- `tests/test_setpoint_detection.py`
- `tests/test_button_injection.py`

## Expected Output

- `esphome/components/tublemetry_display/button_injector.h`
- `esphome/components/tublemetry_display/button_injector.cpp`
- `esphome/components/tublemetry_display/tublemetry_display.h`
- `esphome/components/tublemetry_display/tublemetry_display.cpp`
- `tests/test_auto_refresh.py`

## Verification

uv run pytest tests/ --ignore=tests/test_ladder_cache.py -q 2>&1 | tail -5 && uv run esphome compile esphome/tublemetry.yaml 2>&1 | grep -E '(SUCCESS|ERROR|error|warning)' | tail -10

## Observability Impact

Adds INFO-level auto-refresh trigger log (with cache age in ms) and REFRESHING phase entry/exit logs in ButtonInjector. First-boot NaN path logs a distinct message. These signals let a future agent diagnose whether auto-refresh is firing and whether the REFRESHING phase is completing normally.
