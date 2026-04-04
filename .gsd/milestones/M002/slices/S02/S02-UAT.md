# S02: Setpoint Detection + Temperature Discrimination — UAT

**Milestone:** M002
**Written:** 2026-04-04T13:58:36.078Z

# S02 UAT — Setpoint Detection + Temperature Discrimination

## Preconditions

- Firmware compiled from this branch deployed to tublemetry.local (192.168.0.92) via OTA
- HA connected and showing `sensor.tublemetry_hot_tub_temperature`, `sensor.tublemetry_hot_tub_detected_setpoint`, `sensor.tublemetry_hot_tub_display_state`
- Hot tub powered on with VS300FL4 controller running normally
- USB serial monitor connected for log observation (optional but recommended)

## Test Cases

### TC-01: Initial State — detected_setpoint is Unavailable

**Precondition:** Fresh boot before any set-mode has been triggered.

1. Open HA → Developer Tools → States
2. Find `sensor.tublemetry_hot_tub_detected_setpoint`
3. Observe state

**Expected:** State is `unavailable` or `unknown` (NaN → ESPHome publishes nothing until first value). Temperature sensor shows current water temperature normally.

---

### TC-02: Temperature Sensor Publishes During Normal Operation

**Precondition:** No recent button presses, display showing stable water temperature.

1. Observe `sensor.tublemetry_hot_tub_temperature` in HA history for 2 minutes
2. Observe `sensor.tublemetry_hot_tub_display_state`

**Expected:** Temperature sensor updates steadily with actual water temperature. No sudden spikes or drops. display_state shows "temperature" continuously.

---

### TC-03: Set Mode Entry — Temperature Sensor Suppressed During Setpoint Flash

**Precondition:** Hot tub showing stable temperature (e.g. 98°F).

1. Press the UP or DOWN button on the VS300FL4 panel (or press via HA service call)
2. Immediately watch `sensor.tublemetry_hot_tub_temperature` in HA
3. Watch `sensor.tublemetry_hot_tub_display_state` during the flash sequence

**Expected:** 
- temperature sensor does NOT spike/dip to the setpoint value during the 5-10 second flash sequence
- display_state alternates between "temperature" and "blank" during the flash (this is correct — display state mirrors the physical display)
- Temperature sensor remains at the pre-press water temperature throughout

**Failure indicator:** Temperature history shows a brief spike to the setpoint value (e.g. 102°F when water is 98°F) — this is the regression being fixed.

---

### TC-04: Detected Setpoint Published After Set Mode

**Precondition:** Same session as TC-03 (or new press).

1. After pressing UP/DOWN, observe `sensor.tublemetry_hot_tub_detected_setpoint`
2. Wait for the display to flash setpoint for ~2 seconds then return to water temperature
3. Check the detected_setpoint entity value

**Expected:** detected_setpoint sensor updates to the setpoint value shown on the display (e.g. 102°F). Value appears after the first complete blank→temp→blank confirmation cycle — typically within 1-2 seconds of the press.

---

### TC-05: Setpoint Not Re-Published When Unchanged

**Precondition:** detected_setpoint sensor shows a known value (e.g. 102°F from TC-04).

1. Press UP then DOWN to return to the same setpoint (net zero change)
2. Observe detected_setpoint sensor during and after the button sequence

**Expected:** detected_setpoint sensor does NOT fire an additional state change event if the detected value equals the previously published value. HA history shows no spurious update.

---

### TC-06: Set Mode Timeout — Temperature Resumes Normally

**Precondition:** Somehow the display enters set mode but the blank-frame alternation stops mid-sequence (e.g. controller resets, unusual timing).

1. With serial monitor connected, watch for "Set mode timeout — returning to normal" log message
2. Alternatively: verify via Python tests (test_temperature_after_timeout_publishes_normally)

**Expected:** After 2000ms without a blank frame, the temperature sensor resumes publishing normally. No stuck suppression state. (Primary verification via pytest since this edge case is hard to trigger live.)

---

### TC-07: ButtonInjector Uses Known Setpoint (PROBING Skipped)

**Precondition:** detected_setpoint has been populated (TC-04 completed).

1. Send a setpoint change command from HA: call service `number.set_value` on `number.tublemetry_hot_tub_setpoint` with a value ±2 from current setpoint
2. With serial monitor: watch for "PROBING" state log messages

**Expected:** The button injection sequence goes directly to ADJUSTING (no PROBING phase). Fewer button presses total — the sequence is shorter. With serial monitor: no log lines containing "PROBING" after the setpoint command.

**Note:** PROBING will still appear on first boot before any setpoint has been detected (fallback behavior preserved).

---

### TC-08: New HA Entity Visible, Entity ID Correct

1. Open HA → Settings → Devices & Services → ESPHome → tublemetry device
2. Find the new sensor entity

**Expected:** Entity `sensor.tublemetry_hot_tub_detected_setpoint` visible. Friendly name "Hot Tub Detected Setpoint". Unit °F. No existing entities renamed or removed (R012).

---

### TC-09: Regression — Existing Entities Unchanged

1. Verify `sensor.tublemetry_hot_tub_temperature` still updates
2. Verify `sensor.tublemetry_hot_tub_display_state` still updates
3. Verify `sensor.tublemetry_hot_tub_decode_confidence` still updates
4. Verify `number.tublemetry_hot_tub_setpoint` still accepts commands

**Expected:** All existing entities continue to function identically to pre-S02 behavior. No entity ID changes, no missing entities, no stale values.

---

## Edge Cases

**EC-01: Multiple consecutive setpoint presses.** Press UP three times in succession. Each press should produce a detected_setpoint update with the new value. Temperature sensor remains suppressed throughout.

**EC-02: Very fast display.** If blank-frame alternation resolves in under 500ms, the state machine should still detect and publish correctly (Python tests cover this: test_blank_temp_blank_publishes_setpoint uses immediate timing).

**EC-03: First boot, no setpoint history.** Before any set-mode has been triggered, ButtonInjector falls back to PROBING when a setpoint change is requested. This is correct behavior — verified by existing ButtonInjector tests.

## Automated Test Coverage

All 25 tests in `tests/test_setpoint_detection.py` must pass:

```
uv run pytest tests/test_setpoint_detection.py -v
```

Expected: 25/25 passed. Full suite:

```
uv run pytest tests/ --ignore=tests/test_ladder_capture.py -q
```

Expected: 299/299 passed.
