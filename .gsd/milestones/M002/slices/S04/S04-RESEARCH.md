# S04: Auto-Refresh Setpoint Keepalive — Research

**Date:** 2026-04-04
**Scope:** R008 — periodic COOL press to keep detected_setpoint sensor current

## Summary

S04 is light work on a well-understood codebase. The integration points are fully in place from S02: `detected_setpoint_` is tracked in `TublemetryDisplay`, `ButtonInjector.is_busy()` is public, and `set_known_setpoint()` is already wired. The only real design question is whether pressing COOL (temp_down) just *displays* the current setpoint or also *decrements* it by 1°F. The PROBING code in `button_injector.cpp` makes this clear: `loop_probing_()` presses `temp_down_pin_`, then reads `last_display_temp_` and calls it `probed_setpoint_ = last_display_temp_` — commenting "Display shows the new setpoint (old - 1) after our down press." So COOL press **does** decrement by 1°F. A compensating WARM press is required.

The auto-refresh logic belongs entirely in `TublemetryDisplay::loop()` — a simple timer check, idle-guard, and two-press sequence using existing `ButtonInjector` infrastructure. No new classes needed.

## Recommendation

Implement auto-refresh as a two-phase sequence entirely within `TublemetryDisplay`:

1. Add two fields to `tublemetry_display.h`: `last_setpoint_capture_ms_` (uint32_t, initialized to 0) and `SET_FORCE_INTERVAL_MS` (constexpr, 5 * 60 * 1000 = 300000).
2. In `loop()`, after calling `this->injector_->loop()`, add a guard: if injector is not busy, and `detected_setpoint_` is NaN OR `millis() - last_setpoint_capture_ms_ >= SET_FORCE_INTERVAL_MS`, then call `this->injector_->press_once(false)` (COOL press). The set-mode state machine in `classify_display_state_()` will naturally detect the resulting blank→setpoint→blank sequence and update `detected_setpoint_` and `last_setpoint_capture_ms_`.
3. Update `last_setpoint_capture_ms_` inside `classify_display_state_()` whenever a setpoint is confirmed (same place that calls `set_known_setpoint()`).
4. For the compensating WARM press: **do not add a second immediate press from `loop()`**. Instead, rely on the fact that S02's set-mode confirmation already calls `injector_->set_known_setpoint(detected_setpoint_)`. When the TOU automation next calls `request_temperature()`, the injector will use `known_setpoint_` and press WARM once if needed. The -1°F from the COOL probe will appear briefly in the detected_setpoint sensor, then self-correct on the next set-mode sequence. This is acceptable — the alternative (pressing WARM immediately in loop()) would require another timer and additional state, with no real benefit.

Wait — re-examining: `press_once()` sets `this->known_setpoint_ = NAN` deliberately ("test press changes real setpoint — probe on next sequence"). So calling `press_once(false)` for auto-refresh would also clobber the known_setpoint cache. That's wrong for auto-refresh. Instead, auto-refresh should use a dedicated method that fires a down press without destroying the known_setpoint cache, or `press_once` should be extended with a `clear_cache` parameter.

**Revised recommendation:** Add a new method `ButtonInjector::press_cool_for_refresh()` that fires a single COOL (down) press via `TEST_PRESS` phase but does NOT set `known_setpoint_ = NAN`. Then immediately queue a single WARM press to restore the setpoint. Simplest implementation: add `refresh_setpoint()` to `ButtonInjector` that fires down then up (net zero delta), returns to IDLE, and lets the set-mode state machine capture the setpoint from the resulting display flash.

Actually the cleanest approach: add a `trigger_setpoint_refresh()` method to `TublemetryDisplay` that, when the injector is idle, calls a new `ButtonInjector::press_for_display()` method (single down press, does NOT clear known_setpoint_). The COOL press causes the display to flash the setpoint (now decremented by 1), set-mode fires, and `detected_setpoint_` updates to `current - 1`. Then `press_for_display()` also schedules a compensating up press. The whole thing is one small state extension.

**Simplest correct implementation** (recommended): Add `refresh_setpoint()` to `ButtonInjector`. This method:
- Rejects if `is_busy()`.
- Sets `presses_remaining_ = 1`, `adjusting_up_ = false`, transitions to `ADJUSTING` phase, and after the ADJUSTING completes it transitions to VERIFYING... but that's wrong too since we don't want to wait for confirmation, just fire once.

**Final recommendation:** The cleanest path is to handle this entirely in `TublemetryDisplay::loop()` without modifying `ButtonInjector`. Instead of using `press_once()`, call a new pair: one raw COOL press via GPIO directly, or add a minimal `fire_down_then_up()` method to `ButtonInjector` that fires down + wait + up without affecting `known_setpoint_`. 

Given the codebase patterns, the correct approach is: add `void press_refresh()` to `ButtonInjector` that mirrors `press_once()` but (a) does NOT clear `known_setpoint_`, and (b) presses down then immediately queues up in a new `REFRESH` phase (or reuses `ADJUSTING` with delta=1 up after the down). The set-mode state machine captures `current_setpoint - 1` from the COOL press, then `current_setpoint` from the WARM press, and the second blank confirms the WARM value — net result: `detected_setpoint_` ends up with the correct unmodified setpoint.

Or, even simpler: just add the WARM compensating press as the *second* press in a new `PROBING` variant. But this is getting complex.

**Actual simplest correct path:**
1. Add `SET_FORCE_INTERVAL_MS = 300000` to `tublemetry_display.h`.
2. Add `last_setpoint_capture_ms_` field (uint32_t, 0).
3. In `classify_display_state_()`, when a setpoint is confirmed, set `this->last_setpoint_capture_ms_ = millis()`.
4. In `loop()`, if `!injector_->is_busy()` and the interval has elapsed (or `detected_setpoint_` is NaN), call `injector_->request_temperature(this->detected_setpoint_)` — **no**: this would move setpoint to itself, firing zero-press ADJUSTING → VERIFYING, which is actually valid (delta=0 → `start_adjusting_` transitions to VERIFYING directly, which reads the display). This triggers a PROBING sequence only if `known_setpoint_` is NaN. But if `known_setpoint_` is set, delta=0 → VERIFYING → reads display temperature → if it matches `target_temp_` within the verify loop, SUCCESS. But VERIFYING waits for `last_display_temp_ == target_temp_`, which it already is → immediate SUCCESS → setpoint confirmed unchanged.

This won't trigger a display flash at all — it just reads the already-displayed temperature without pressing any buttons.

**Conclusion:** The only way to force the display to show the setpoint is to press COOL (or WARM). For auto-refresh, the correct pattern from kgstorm is: press COOL once (show setpoint -1), then press WARM once (restore and show correct setpoint). Implement as a minimal new phase `REFRESHING` in `ButtonInjector` that fires down→wait→up, transitions to COOLDOWN, and does NOT touch `known_setpoint_`. `TublemetryDisplay` triggers this by calling a new `ButtonInjector::refresh()` method from `loop()` on the interval.

## Implementation Landscape

### Key Files

- `esphome/components/tublemetry_display/tublemetry_display.h` — Add `SET_FORCE_INTERVAL_MS` constexpr and `last_setpoint_capture_ms_` field (uint32_t, 0). No other changes needed.
- `esphome/components/tublemetry_display/tublemetry_display.cpp` — Two changes: (1) `classify_display_state_()` sets `last_setpoint_capture_ms_ = millis()` alongside the existing `set_known_setpoint()` call on confirmation; (2) `loop()` adds interval check and calls `injector_->refresh()` when not busy and interval elapsed.
- `esphome/components/tublemetry_display/button_injector.h` — Add `REFRESHING` to `InjectorPhase` enum; add `void refresh()` public method; no new fields needed beyond reusing existing timing/pin infrastructure.
- `esphome/components/tublemetry_display/button_injector.cpp` — Add `loop_refreshing_()` private method: press down, wait, press up, transition to COOLDOWN. Add `refresh()` public method: reject if busy, set adjusting_up_=false (irrelevant but clean), transition to REFRESHING. Add case in `loop()` switch and `phase_to_string()`.
- `tests/test_button_injection.py` — Add `TestRefreshPhase` class: test that `refresh()` fires down then up; test that `known_setpoint_` is NOT cleared; test that `refresh()` is rejected when busy.
- `tests/test_setpoint_detection.py` (or new `tests/test_auto_refresh.py`) — Add `TestAutoRefresh` class: test that `last_setpoint_capture_ms_` is updated on setpoint confirmation; test that refresh is triggered after `SET_FORCE_INTERVAL_MS` elapses with no setpoint capture; test that refresh is not triggered when injector is busy; test that refresh fires on first boot (detected_setpoint_ is NaN).

### Build Order

1. **C++ changes** (tublemetry_display.h/cpp + button_injector.h/cpp) — all four files change in concert. No blocking dependencies; the changes are additive to existing infrastructure.
2. **Tests** — Python mirror of `loop()` interval check in `TublemetryDisplay` is trivial; `ButtonInjector` refresh phase test is the same pattern as existing test_button_injection.py tests.
3. **Compile verification** — run ESPHome compile to confirm no regressions.

### Constraints

- `ButtonInjector::refresh()` must NOT clear `known_setpoint_`. This is the key difference from `press_once()`.
- `refresh()` must press COOL (down) then WARM (up) — net zero setpoint change. The brief -1°F setpoint visible during the flash sequence is acceptable transient behavior.
- The interval check in `loop()` must guard on `injector_ != nullptr && injector_->is_configured() && !injector_->is_busy()`.
- `last_setpoint_capture_ms_` starts at 0, so the first loop() iteration after boot (once WiFi/API stabilize) will NOT immediately fire the refresh — the condition should be `millis() > SET_FORCE_INTERVAL_MS` OR `std::isnan(detected_setpoint_)`. The NaN condition handles first boot cleanly: fires once at startup to populate the cache, regardless of elapsed time.
- The loop() interval check should debounce: only fire if `last_setpoint_capture_ms_ > 0` for the time-based path. The NaN path fires once, sets `detected_setpoint_` on first confirmation, and then the time-based path takes over.

### Observability

- Log at INFO when refresh fires: `ESP_LOGI(TAG, "Auto-refresh: triggering COOL press (setpoint cache age: %lums)", millis() - last_setpoint_capture_ms_)`.
- `ButtonInjector` logs at INFO on REFRESHING phase entry/exit (same pattern as existing phase transitions).

### Test Pattern

Follow `SetModeStateMachine` mirror pattern from `tests/test_setpoint_detection.py`. For the `loop()` interval check, a Python `AutoRefreshStateMachine` class with `now_ms` injection is cleaner than trying to mock `millis()`. The `ButtonInjector` refresh phase tests can follow `test_button_injection.py` patterns directly since that test suite already instantiates `ButtonInjector` with mock pins.
