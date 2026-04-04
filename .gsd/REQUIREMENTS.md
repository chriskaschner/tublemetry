# Requirements

This file is the explicit capability and coverage contract for the project.

## Active

### R001 — Checksum validation rejects corrupt frames
- Class: quality-attribute
- Status: active
- Description: 5 always-zero bits in each 24-bit frame (p1 bits 6,3,1,0 and p4 bit 0) are checked before any processing. Frames that fail are logged and dropped.
- Why it matters: Corrupt frames that happen to decode as valid 7-seg characters currently pass through undetected. Free integrity gate that costs nothing at runtime.
- Source: research (kgstorm)
- Primary owning slice: M002/S01
- Supporting slices: none
- Validation: unmapped
- Notes: Startup dashes (0x01) will fail checksum — this is correct behavior. Display state for startup should be handled separately if needed.

### R002 — Stability filtering requires N consecutive matching frames before publishing
- Class: quality-attribute
- Status: active
- Description: Require 3 consecutive identical decoded frames before publishing any value to HA. Prevents single noise-but-valid frames from briefly appearing in sensor history.
- Why it matters: Currently a single clean-but-wrong frame gets published immediately. Stability filtering is the difference between noisy and trustworthy telemetry.
- Source: research (kgstorm)
- Primary owning slice: M002/S01
- Supporting slices: none
- Validation: unmapped
- Notes: kgstorm uses STABLE_THRESHOLD=3. Configurable threshold is a nice-to-have but not required.

### R003 — Temperature sensor only publishes steady-state water temperature
- Class: core-capability
- Status: active
- Description: The temperature sensor must not publish values during setpoint flash sequences. When the display alternates between a temperature value and blank frames (setpoint flashing), those values are routed to the setpoint sensor, not the temperature sensor.
- Why it matters: Setpoint flashes currently pollute the temperature history in HA. Every TOU automation trigger causes a visible spike/dip in the temperature graph that isn't a real temperature change.
- Source: user
- Primary owning slice: M002/S02
- Supporting slices: none
- Validation: unmapped
- Notes: The blank-frame alternation pattern (0x00/0x00/0x00 frames interleaved with temperature frames) is the detection mechanism. kgstorm uses a 2-second timeout to exit set mode.

### R004 — Separate setpoint sensor tracks the controller's actual setpoint
- Class: core-capability
- Status: active
- Description: A dedicated HA sensor publishes the VS300FL4's actual setpoint as detected from the display flash pattern. This is the real setpoint the controller is using, not what HA last commanded.
- Why it matters: Provides ground truth for the controller's setpoint. Enables verification that TOU automation commands actually took effect. Eliminates the need for the button injector's PROBING phase.
- Source: user
- Primary owning slice: M002/S02
- Supporting slices: M002/S04
- Validation: unmapped
- Notes: Setpoint is detected when the display enters "set mode" (blank-frame alternation). The sensor should update with stability filtering to prevent transient misreads.

### R005 — Heater status exposed as HA binary sensor
- Class: differentiator
- Status: active
- Description: Bit 2 of p1 (the first 7-bit segment group in each frame) indicates heater on/off. Exposed as a binary sensor in HA.
- Why it matters: Free telemetry about whether the heater is actively running. Useful for energy tracking, diagnostics, and correlating temperature rise rate with heater cycles.
- Source: research (kgstorm)
- Primary owning slice: M002/S03
- Supporting slices: none
- Validation: unmapped
- Notes: kgstorm uses heater hysteresis (instant on, delayed off to prevent flicker). Hysteresis is deferred to R014.

### R006 — Pump status exposed as HA binary sensor
- Class: differentiator
- Status: active
- Description: Bit 2 of p4 (the 3 status bits at the end of each frame) indicates pump on/off. Exposed as a binary sensor in HA.
- Why it matters: Shows whether the circulation pump is running. Useful for diagnostics and verifying the tub is in active mode vs idle.
- Source: research (kgstorm)
- Primary owning slice: M002/S03
- Supporting slices: none
- Validation: unmapped
- Notes: Bit position from kgstorm analysis. Will be verified against live wire data during implementation.

### R007 — Light status exposed as HA binary sensor
- Class: differentiator
- Status: active
- Description: Bit 1 of p4 indicates light on/off. Exposed as a binary sensor in HA.
- Why it matters: Shows whether the tub light is on. Minor but free.
- Source: research (kgstorm)
- Primary owning slice: M002/S03
- Supporting slices: none
- Validation: unmapped
- Notes: Bit position from kgstorm analysis. Will be verified against live wire data during implementation.

### R008 — Auto-refresh presses COOL every 5 minutes to keep setpoint sensor current
- Class: continuity
- Status: active
- Description: When no setpoint has been captured from the display for 5 minutes, the firmware automatically presses the COOL button once to force the display to flash the current setpoint. This keeps the setpoint sensor in HA current even when nobody touches the panel.
- Why it matters: Without periodic refresh, the setpoint sensor goes stale between TOU automation triggers. The auto-refresh ensures HA always shows the real setpoint.
- Source: research (kgstorm)
- Primary owning slice: M002/S04
- Supporting slices: none
- Validation: unmapped
- Notes: Must not fire while button injector is busy. kgstorm uses SET_FORCE_INTERVAL_MS = 5 * 60 * 1000. The COOL press changes setpoint by -1°F, so the firmware should immediately press WARM once to restore it — or use a different button that triggers display without changing setpoint. Needs investigation.

### R009 — Button injector uses known setpoint from display state machine
- Class: core-capability
- Status: active
- Description: When the setpoint detection state machine has a known setpoint, the button injector uses it directly for delta calculation instead of entering the PROBING phase (press down to discover current setpoint). PROBING remains as fallback for first boot or after setpoint cache invalidation.
- Why it matters: Eliminates one unnecessary button press per setpoint change. Faster TOU transitions. Simpler state machine flow.
- Source: inferred
- Primary owning slice: M002/S02
- Supporting slices: none
- Validation: unmapped
- Notes: The display state machine's known setpoint feeds into ButtonInjector::known_setpoint_ directly.

### R010 — All existing tests pass after changes
- Class: quality-attribute
- Status: active
- Description: Every test in the existing test suite (pytest) must pass after M002 changes. No regressions.
- Why it matters: The test suite validates the decode pipeline, 7-seg table cross-check, YAML config, button injection logic, and frame parsing. Regressions here mean broken firmware.
- Source: inferred
- Primary owning slice: M002/S01
- Supporting slices: all
- Validation: unmapped
- Notes: `uv run pytest` is the command.

### R011 — Firmware compiles and boots clean on ESP32
- Class: quality-attribute
- Status: active
- Description: `uv run esphome compile esphome/tublemetry.yaml` succeeds. OTA flash to the running ESP32 at tublemetry.local succeeds. Boot log shows no crashes, watchdog resets, or error loops for 60 seconds.
- Why it matters: The firmware runs on real hardware. Compile + flash + boot is the minimum bar.
- Source: inferred
- Primary owning slice: M002/S01
- Supporting slices: all
- Validation: unmapped
- Notes: OTA at 192.168.0.92 / tublemetry.local.

### R012 — Existing HA entity IDs, dashboard cards, and TOU automation references unchanged
- Class: continuity
- Status: active
- Description: All existing HA entity IDs must be preserved exactly: `sensor.tublemetry_hot_tub_temperature`, `number.tublemetry_hot_tub_setpoint`, `sensor.tublemetry_hot_tub_display_state`, `sensor.tublemetry_hot_tub_decode_confidence`, etc. Dashboard cards in `ha/dashboard.yaml` and TOU automation in `ha/tou_automation.yaml` must continue to reference valid entities.
- Why it matters: Renaming entities breaks automations, history, and dashboard configs. The TOU automation is live and running overnight.
- Source: user
- Primary owning slice: all
- Supporting slices: none
- Validation: unmapped
- Notes: New entities (setpoint sensor, binary sensors) get new IDs. Existing entities keep their current IDs.

## Validated

(None yet — M002 has not started.)

## Deferred

### R013 — Error code text sensor
- Class: differentiator
- Status: deferred
- Description: Decode and publish VS300FL4 error codes (OH, IC, SA, Sb, etc.) as a text sensor in HA, with plain-English translations.
- Why it matters: kgstorm has a full error code decoder with stability filtering. Useful for diagnostics but not needed for TOU automation.
- Source: research (kgstorm)
- Primary owning slice: none
- Supporting slices: none
- Validation: unmapped
- Notes: Deferred because error codes are rare in normal operation and the current display_state sensor already classifies OH, ICE, etc.

### R014 — Heater hysteresis (instant on, delayed off)
- Class: quality-attribute
- Status: deferred
- Description: Heater binary sensor turns on immediately when bit is set, but only turns off after the bit has been clear for a configurable timeout (e.g. 1 second). Prevents rapid flicker in HA.
- Why it matters: kgstorm implements this to smooth the heater status display. Nice polish but not essential.
- Source: research (kgstorm)
- Primary owning slice: none
- Supporting slices: none
- Validation: unmapped
- Notes: Can be added in a later milestone if heater flicker is observed.

## Out of Scope

(None for M002.)

## Traceability

| ID | Class | Status | Primary owner | Supporting | Proof |
|---|---|---|---|---|---|
| R001 | quality-attribute | active | M002/S01 | none | unmapped |
| R002 | quality-attribute | active | M002/S01 | none | unmapped |
| R003 | core-capability | active | M002/S02 | none | unmapped |
| R004 | core-capability | active | M002/S02 | M002/S04 | unmapped |
| R005 | differentiator | active | M002/S03 | none | unmapped |
| R006 | differentiator | active | M002/S03 | none | unmapped |
| R007 | differentiator | active | M002/S03 | none | unmapped |
| R008 | continuity | active | M002/S04 | none | unmapped |
| R009 | core-capability | active | M002/S02 | none | unmapped |
| R010 | quality-attribute | active | M002/S01 | all | unmapped |
| R011 | quality-attribute | active | M002/S01 | all | unmapped |
| R012 | continuity | active | all | none | unmapped |
| R013 | differentiator | deferred | none | none | unmapped |
| R014 | quality-attribute | deferred | none | none | unmapped |

## Coverage Summary

- Active requirements: 12
- Mapped to slices: 12
- Validated: 0
- Unmapped active requirements: 0
