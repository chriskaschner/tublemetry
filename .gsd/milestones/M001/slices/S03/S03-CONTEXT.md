---
id: S03
milestone: M001
status: ready
---

# S03: Button Injection + Closed-Loop Control — Context

## Goal

Harden the existing button injection and closed-loop verification system for unattended reliability, add retry/drift-correction logic, error code handling, manual override detection, and HA-side automation improvements.

## Why this Slice

The system is already running in production — ESP32 reads the display, injects button presses, and HA runs TOU automations on schedule. But it hasn't had enough reps to trust unattended: missed button presses cause setpoint errors (observed: commanding 104°F from 99°F but landing at 102°F), there's no retry logic, no drift correction, no error code handling, and the HA-side automation needs hardening. This slice closes the gap between "working prototype" and "reliable unattended system."

## Scope

### In Scope

- **Retry logic on verification failure**: When closed-loop verification detects a mismatch (display shows wrong temp after adjustment), automatically retry the sequence (probe → re-calculate delta → adjust again) rather than accepting the TIMEOUT result
- **Drift detection + auto-correction with notification**: If the display shows a temperature that diverges from the last commanded setpoint (missed press, manual panel change, power cycle), auto-correct back to the TOU target AND send an HA notification so the user knows what happened
- **Error code suppression**: When the display shows OH (overheat), ICE (freeze protection), or other error codes, pause TOU automation and send an HA notification — don't inject buttons during board protection events
- **Manual override detection — physical panel**: If someone presses buttons on the physical panel, detect the unexpected setpoint change and pause TOU automation (don't fight the human). User re-enables when ready.
- **Manual override detection — HA app**: If the user manually changes the setpoint via the HA app (outside of TOU automation), treat it the same as a panel override — pause TOU until re-enabled
- **TOU on/off toggle**: An `input_boolean` in HA that completely enables/disables TOU automation. User flips this when they want manual control (e.g., party, maintenance, guests)
- **Weather gating**: Skip TOU transitions when outdoor temperature is below 35°F (freeze risk) or during extreme conditions
- **Heating tracker fixes**: The `heating_tracker.yaml` references `climate.hot_tub` which doesn't exist — fix to use the actual `number.tublemetry_hot_tub_setpoint` and `sensor.tublemetry_hot_tub_temperature` entities
- **HA notification plumbing**: Notifications for drift correction, error codes, verification failures, and override detection (via HA `notify` or `persistent_notification`)
- **Button timing investigation**: The current defaults (200ms press, 300ms gap) are causing missed presses. Investigate whether longer press duration, longer gap, or both are needed. The setpoint flash on the VS300FL4 display lasts approximately 2000ms — timing must account for this.

### Out of Scope

- **Lights/Jets control**: Same circuit pattern but not needed for TOU. Separate slice.
- **Board-powered operation**: USB/tub-powered hardware change. Not firmware.
- **Energy cost tracking / utility meter**: Deferred to after reliability is proven.
- **Community publication**: Phase 3 milestone.
- **New ESP32 hardware**: Current board is working. Hardware issues are resolved.
- **Dashboard redesign**: Current cards are adequate. Polish is future work.

## Constraints

- **System is live in production**: All changes must be deployable via OTA without breaking the running system. No changes that require physical access or reflashing via USB.
- **Decision D001 is locked**: Temperature handling uses raw integer values with no unit conversion. ESP32 publishes display integers, HA declares °F. No climate entity — use sensor + number entities.
- **Setpoint flash timing is ~2000ms**: The VS300FL4 display shows the setpoint for approximately 2 seconds after a button press before returning to current temperature. The injector must account for this window when reading display confirmation.
- **Existing probe→adjust→verify→cooldown state machine**: The `ButtonInjector` class structure is solid. Retry logic should extend it, not rewrite it.
- **Arduino framework only**: The ESP32-D0WD-V3 rev3.1 board boot-loops with ESP-IDF; Arduino framework is required (per KNOWLEDGE.md).

## Integration Points

### Consumes

- `esphome/components/tublemetry_display/button_injector.{h,cpp}` — existing state machine for button injection with probe/adjust/verify/cooldown phases
- `esphome/components/tublemetry_display/tublemetry_display.{h,cpp}` — display decoder that feeds temperature and display state to the injector via `feed_display_temperature()` and `classify_display_state_()`
- `esphome/components/tublemetry_display/tublemetry_setpoint.{h,cpp}` — number entity that triggers `request_temperature()` on the injector
- `esphome/tublemetry.yaml` — production ESPHome config with GPIO pins, timing defaults, WiFi/OTA/API settings
- `ha/tou_automation.yaml` — existing TOU schedule automation using `number.set_value`
- `ha/heating_tracker.yaml` — heating duration tracker (currently broken — references nonexistent `climate.hot_tub`)
- `ha/dashboard.yaml` — existing Lovelace cards
- `ha/templates.yaml` — outdoor temperature template sensor

### Produces

- Updated `button_injector.{h,cpp}` with retry logic, retry count limits, and retry state tracking
- Updated `tublemetry_display.{h,cpp}` with drift detection logic (compare display reading vs last commanded setpoint, detect unsolicited changes)
- Updated `tublemetry.yaml` with tuned timing parameters and any new diagnostic entities (retry count, drift events, injection result sensor)
- Updated `ha/tou_automation.yaml` with weather gating, TOU toggle condition, error code suppression, and override-aware conditions
- Fixed `ha/heating_tracker.yaml` using correct entity IDs (`number.*` and `sensor.*` instead of `climate.*`)
- New HA helpers (input_boolean for TOU toggle, notifications for drift/errors/overrides)
- New or updated `ha/templates.yaml` with any derived sensors needed for override detection

## Open Questions

- **Retry limit**: How many retry attempts before giving up and notifying? Current thinking: 3 retries max, then notify and accept the current state. Prevents infinite retry loops.
- **Drift detection window**: How long to wait after a TOU transition before flagging unexpected display changes as "drift" vs "normal settling"? Current thinking: 60 seconds after a successful verification, any display change not commanded by the ESP is flagged.
- **Override resume behavior**: When the user re-enables TOU after a manual override, should it immediately set the correct temperature for the current TOU window, or wait for the next scheduled transition? Current thinking: immediately apply the correct setpoint for the current time window.
- **Press timing tuning**: The 200ms/300ms defaults may be too aggressive. Need to test with 300ms/500ms or even 500ms/700ms. The 2-second setpoint flash window suggests the board needs more time to register each press. This should be investigated empirically during this slice, not pre-decided.
- **Notification target**: Which HA notification service to use (mobile app, persistent notification, both)? Current thinking: `persistent_notification.create` for in-dashboard alerts, plus mobile push if configured.
