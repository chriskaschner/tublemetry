# M002: Display Intelligence — Context

**Gathered:** 2026-04-03
**Status:** Ready for planning

## Project Description

Harden the Tublemetry display decode pipeline and add display intelligence features adapted from kgstorm's Balboa-GS100-with-VL260-topside project. The VS300FL4 uses the same synchronous clock+data protocol with 24-bit frames, so the techniques transfer directly — and we can verify bit positions against live wire data from the running ESP32.

## Why This Milestone

The M001 firmware works but is naive about frame quality and display modes. It publishes the first clean frame it sees (no stability filtering), has no frame integrity checks (no checksum), can't tell a setpoint flash from a real temperature reading (pollutes HA history), ignores the status bits in every frame (heater/pump/light), and has no way to keep the setpoint sensor current between TOU automation triggers. kgstorm solved all of these problems. This milestone adapts their proven techniques into Tublemetry's architecture.

## User-Visible Outcome

### When this milestone is complete, the user can:

- Look at the HA temperature history and see clean data with no setpoint flash spikes
- See the actual controller setpoint in a dedicated HA sensor
- See heater, pump, and light on/off status as binary sensors in HA
- Trust that the temperature readings are real (3 consecutive matching frames required)
- Know the setpoint stays current even when nobody touches the panel (auto-refresh)

### Entry point / environment

- Entry point: Home Assistant dashboard + TOU automation
- Environment: ESP32 at tublemetry.local (192.168.0.92), OTA flash, HA integration
- Live dependencies involved: VS300FL4 controller, RJ45 tee, WiFi, Home Assistant API

## Completion Class

- Contract complete means: firmware compiles, all tests pass (existing + new), YAML validates
- Integration complete means: OTA flash succeeds, ESP32 boots clean, HA entities appear with correct IDs
- Operational complete means: temperature history stays clean during TOU transitions, setpoint sensor updates when automation fires, binary sensors reflect actual hardware state

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- A TOU automation trigger changes the setpoint and the setpoint sensor updates without polluting the temperature sensor history
- Heater binary sensor reflects actual heating state (on when heater is running, off when idle)
- A manually-induced corrupt frame (or noise) is logged and dropped, not published
- The auto-refresh fires after 5 minutes of no setpoint capture and the setpoint sensor updates

## Risks and Unknowns

- Status bit positions (heater=p1 bit 2, pump=p4 bit 2, light=p4 bit 1) are from kgstorm's GS100/VL260 analysis — need verification against VS300FL4 live wire data via the raw_hex sensor, but the frame structure is confirmed identical
- Auto-refresh COOL press interaction with button injector — must not fire while injector is busy, and COOL decrements setpoint by 1°F which needs compensating (press WARM once after) unless a neutral button exists
- Blank-frame alternation timing may differ between GS100 and VS300FL4 — the SET_MODE_TIMEOUT_MS may need tuning after observing real behavior

## Existing Codebase / Prior Art

- `esphome/components/tublemetry_display/tublemetry_display.cpp` — main decode pipeline, `process_frame_()` is the focal point for S01 and S02 changes
- `esphome/components/tublemetry_display/tublemetry_display.h` — component class, sensor pointers, ISR data structures
- `esphome/components/tublemetry_display/button_injector.cpp` — non-blocking state machine for button injection, PROBING phase to be modified in S02
- `esphome/components/tublemetry_display/button_injector.h` — injector class with `known_setpoint_` cache
- `esphome/components/tublemetry_display/__init__.py` — ESPHome codegen, config schema, pin setup
- `esphome/components/tublemetry_display/sensor.py` — sensor platform (temperature, decode_confidence)
- `esphome/components/tublemetry_display/text_sensor.py` — text sensor platform (display_string, raw_hex, display_state, etc.)
- `esphome/components/tublemetry_display/number.py` — setpoint number entity
- `esphome/tublemetry.yaml` — main ESPHome config
- `ha/tou_automation.yaml` — live TOU automation targeting `number.tublemetry_hot_tub_setpoint`
- `ha/dashboard.yaml` — HA dashboard cards
- `tests/test_mock_frames.py` — frame decode pipeline tests with real captured data
- `tests/test_button_injection.py` — button injector algorithm tests
- kgstorm reference: `https://github.com/kgstorm/Balboa-GS100-with-VL260-topside` — `esp32-spa/inputs/esp32-spa.h` contains the setpoint detection state machine, stability filtering, checksum validation, status bit decoding, and auto-refresh logic

> See `.gsd/DECISIONS.md` for all architectural and pattern decisions — it is an append-only register; read it during planning, append to it during execution.

## Relevant Requirements

- R001-R002 — Frame integrity (checksum + stability)
- R003-R004, R009 — Setpoint detection and temperature discrimination
- R005-R007 — Status bit binary sensors
- R008 — Auto-refresh setpoint keepalive
- R010-R011 — Test and build quality gates
- R012 — Entity ID and HA config continuity

## Scope

### In Scope

- Checksum validation (5 always-zero bits per frame)
- Stability filtering (N consecutive matching frames before publish)
- Setpoint detection via blank-frame alternation pattern
- Separate setpoint sensor in HA
- Temperature sensor filtered to exclude setpoint flashes
- Heater, pump, light binary sensors from status bits
- Auto-refresh COOL press to keep setpoint current
- Button injector integration with display-detected setpoint
- New tests for all new features
- Dashboard updates to add new sensors
- OTA flash and boot verification

### Out of Scope / Non-Goals

- Temperature unit conversion (D001 — permanently settled)
- Error code text sensor (R013 — deferred)
- Heater hysteresis (R014 — deferred)
- Protocol documentation updates (future milestone)
- Community contribution to kgstorm (future)

## Technical Constraints

- All changes must compile under ESPHome with Arduino framework on ESP32
- ISR code must remain IRAM-safe — no heap allocation, no Serial, no floating-point in interrupt context
- Stability filtering and setpoint detection run in `loop()`, not ISR — ISR only samples bits
- New entities must use the `tublemetry_display` platform namespace for ESPHome codegen
- Existing entity IDs cannot change (R012)

## Integration Points

- Home Assistant API — new binary_sensor entities for heater/pump/light, new sensor entity for detected setpoint
- Button injector — auto-refresh must coordinate with injection sequences (don't press COOL while injector is busy)
- TOU automation — unchanged, but setpoint sensor provides verification that commands took effect
- Dashboard — new cards for binary sensors and setpoint sensor

## Open Questions

- Does COOL press always decrement setpoint by 1°F, or does it just toggle the display to show setpoint without changing it? kgstorm presses COOL and it triggers the setpoint display flash. If it also decrements, we need a compensating WARM press. If it just shows the current value, no compensation needed. Needs testing on the real tub.
- What's the right SET_MODE_TIMEOUT_MS for the VS300FL4? kgstorm uses 2000ms. May need tuning after observing real display behavior.
