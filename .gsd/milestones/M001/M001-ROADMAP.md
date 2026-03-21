# M001: RS-485 Display Reading

**Vision:** User can see current hot tub water temperature in Home Assistant, read from the VS300FL4 display stream via ESP32, creating the foundation for later closed-loop control.

## Success Criteria

- ESP32 decodes the VS300FL4 display stream and extracts current water temperature
- Home Assistant shows a useful climate entity with current temperature populated
- Ladder capture and lookup-table validation close the remaining display decoding ambiguity

## Slices

- [x] **S01: RS-485 Display Reading** `risk:medium` `depends:[]`
  > After this: Python decode library, ESPHome display-reading component, and ladder-capture tooling are complete and tested.
- [ ] **S02: Firmware Hardening — WiFi, OTA, HA Integration** `risk:medium` `depends:[S01]`
  > After this: ESP32 reliably connects to WiFi, supports OTA updates, exposes all entities in Home Assistant with proper diagnostics and recovery mechanisms.
- [ ] **S03: Button Injection + Closed-Loop Control** `risk:medium` `depends:[S02]`
  > After this: user can set tub temperature from Home Assistant with closed-loop verification and drift correction.
