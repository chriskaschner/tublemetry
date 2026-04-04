# Tubtron

## What This Is

A hot tub automation system that controls a Balboa VS300FL4 controller via ESP32 and Home Assistant. It reads the synchronous clock+data display stream via GPIO interrupts, decodes 7-segment frames to extract water temperature, and injects button presses through AQY212EH photorelays to adjust the setpoint. A Time-of-Use automation in HA shifts the setpoint on MGE Rg-2A rate windows, saving ~$10/month without manual intervention.

## Core Value

The tub automatically lowers its setpoint during on-peak hours and raises it before evening use — no human involvement required.

## Current State

M001 is functionally complete. The ESP32 decodes display frames, publishes temperature to HA via a sensor entity, accepts setpoint commands via a number entity, and executes button injection sequences with closed-loop verification. WiFi, OTA, safe mode, and captive portal fallback are all working. The TOU automation is live and targeting `number.tublemetry_hot_tub_setpoint` with plain °F values.

Known gaps: the temperature sensor can't distinguish setpoint flashes from actual temperature (pollutes history), status bits in each frame are extracted but ignored, no frame-level integrity checks (checksum or stability filtering), and no periodic setpoint refresh to keep HA in sync.

## Architecture / Key Patterns

- **ESP32 firmware:** ESPHome external component (`tublemetry_display`), Arduino framework, GPIO interrupt-driven clock+data sampling
- **Display protocol:** Synchronous 24-bit frames at 60Hz: [digit1:7][digit2:7][digit3:7][status:3], MSB-first
- **Button injection:** `ButtonInjector` class with non-blocking state machine (IDLE→PROBING→ADJUSTING→VERIFYING→COOLDOWN)
- **Setpoint control:** `TublemetrySetpoint` number entity delegates to `ButtonInjector::request_temperature()`
- **HA integration:** sensor (temperature), number (setpoint), text_sensor (diagnostics), binary_sensor (API status)
- **Unit handling (D001):** ESP32 publishes raw integer display values. HA owns the unit meaning (°F). No conversion anywhere.
- **TOU automation:** `ha/tou_automation.yaml` targets `number.tublemetry_hot_tub_setpoint` with weekday/weekend schedules
- **Dashboard:** `ha/dashboard.yaml` with gauge, entities, history graph, diagnostics cards

## Capability Contract

See `.gsd/REQUIREMENTS.md` for the explicit capability contract, requirement status, and coverage mapping.

## Milestone Sequence

- [x] M001: RS-485 Display Reading — ESP32 decodes VS300FL4 display stream, exposes climate entity in HA, button injection with closed-loop control
- [ ] M002: Display Intelligence — Frame integrity, setpoint detection, status bit sensors, auto-refresh keepalive
