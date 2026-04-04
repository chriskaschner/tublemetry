# M002: 

## Vision
Harden the Tublemetry display decode pipeline with frame integrity checks (checksum validation, stability filtering), add display intelligence (setpoint detection via blank-frame alternation, temperature/setpoint discrimination), expose status bit telemetry (heater/pump/light binary sensors), and keep the setpoint sensor current with periodic auto-refresh. Adapted from kgstorm's proven techniques, verified against live VS300FL4 wire data.

## Slice Overview
| ID | Slice | Risk | Depends | Done | After this |
|----|-------|------|---------|------|------------|
| S01 | Frame Integrity — Checksum + Stability Filter | medium | — | ✅ | After this: firmware rejects corrupt frames via checksum validation and requires 3 consecutive matching frames before publishing. Temperature history is cleaner with no single-frame noise spikes. Verified by tests + compile + existing HA entities unchanged. |
| S02 | Setpoint Detection + Temperature Discrimination | high | S01 | ✅ | After this: HA shows a separate detected-setpoint sensor that tracks the controller's actual setpoint. Temperature sensor no longer publishes setpoint flashes. Button injector uses display-detected setpoint instead of PROBING phase. |
| S03 | Status Bit Binary Sensors | low | S01 | ✅ | After this: heater, pump, and light status appear as binary sensors in HA. Dashboard shows new status card. |
| S04 | Auto-Refresh Setpoint Keepalive | low | S02 | ✅ | After this: setpoint sensor stays current — firmware presses COOL every 5 minutes when no setpoint has been captured, keeping HA in sync with the controller even when nobody touches the panel. |
