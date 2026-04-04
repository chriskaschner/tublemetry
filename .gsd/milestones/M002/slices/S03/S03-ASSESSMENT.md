---
sliceId: S03
uatType: artifact-driven
verdict: PASS
date: 2026-04-04T22:20:00.000Z
---

# UAT Result — S03: Status Bit Binary Sensors

## Checks

| Check | Mode | Result | Notes |
|-------|------|--------|-------|
| **TC-01: Binary sensor entities appear in HA** | artifact | PASS | `esphome/tublemetry.yaml` lines 96–107 declare `binary_sensor: platform: tublemetry_display` with `heater` (name: "Hot Tub Heater"), `pump` (name: "Hot Tub Pump"), `light` (name: "Hot Tub Light"). ESPHome generates entity IDs: `binary_sensor.tublemetry_hot_tub_heater`, `binary_sensor.tublemetry_hot_tub_pump`, `binary_sensor.tublemetry_hot_tub_light` — all three match UAT expectation. ESPHome compile `[SUCCESS]` confirms codegen path executes without error. Live HA entity visibility requires human follow-up after OTA flash. |
| **TC-02: Heater sensor reflects display bit state** | human-follow-up | NEEDS-HUMAN | Bit extraction logic verified: `p1_full = (frame_bits >> 17) & 0x7F; heater_on = (p1_full >> 2) & 0x01` (tublemetry_display.cpp line 307). 9 extraction tests pass (`TestStatusBitExtraction`, `TestChecksumCompatibility`). Physical panel comparison requires live observation after OTA flash. Status bit position (p1 bit 2 = heater) sourced from kgstorm analysis — not yet confirmed against live wire capture. |
| **TC-03: Pump sensor reflects pump state** | human-follow-up | NEEDS-HUMAN | Bit extraction: `pump_on = (status >> 2) & 0x01` where `status = frame_bits & 0x07` (p4 bits 2-0). `TestStatusBitExtraction::test_pump_on_when_status_bit2_set/clear` and bit-isolation tests pass. Physical panel comparison requires live observation. |
| **TC-04: Light sensor reflects light state / toggles** | human-follow-up | NEEDS-HUMAN | Bit extraction: `light_on = (status >> 1) & 0x01`. `TestStatusBitExtraction::test_light_on_when_status_bit1_set/clear` pass. Toggle response: `test_transition_true_to_false_publishes` and `test_rapid_toggle_publishes_every_change` pass — any change to the bit publishes immediately. Frame cycle ~17ms × stable_threshold → <50ms response. Physical toggle test requires live hardware. |
| **TC-05: No spurious state changes when stable** | artifact | PASS | `test_stable_sequence_single_publish` verifies True×4 → single publish. `test_same_value_twice_does_not_republish` and `test_same_false_twice_does_not_republish` both pass. `int8_t` last-state trackers (initialized -1) only publish when current != last (tublemetry_display.cpp lines 310–320). 8 TestPublishOnChange tests covering all combinations pass. |
| **TC-06: Dashboard Card 6 "Hot Tub Status" renders** | artifact | PASS | `ha/dashboard.yaml` lines 74–82: `type: entities`, `title: Hot Tub Status`, three entity rows — `binary_sensor.tublemetry_hot_tub_heater` (name: Heater), `binary_sensor.tublemetry_hot_tub_pump` (name: Pump), `binary_sensor.tublemetry_hot_tub_light` (name: Light). Card structure correct. Live HA rendering requires human follow-up. |
| **TC-07: Existing temperature and setpoint sensors unaffected** | artifact | PASS | `sensor.tublemetry_hot_tub_temperature` and `number.tublemetry_hot_tub_setpoint` present in `ha/dashboard.yaml` at lines 9, 27, 29, 40, 51, 53. `test_esphome_yaml.py::TestProductionConfig::test_status_binary_sensor` and temperature/setpoint tests pass. 336/336 pytest tests pass with no regressions vs pre-S03 baseline. |
| **TC-08: First publish on boot** | artifact | PASS | `int8_t last_heater_{-1}`, `last_pump_{-1}`, `last_light_{-1}` initialized in class definition (tublemetry_display.h lines 128–130). `test_first_frame_always_publishes` verifies last=-1 → True publishes, last=-1 → False publishes. First valid frame through the checksum gate will trigger publish for all three sensors regardless of state. |
| **Edge: All three sensors on simultaneously** | artifact | PASS | `test_all_three_on_simultaneously` and `test_all_status_combinations[6-True-True]` (all bits set) pass. `test_independent_state_per_sensor` verifies per-sensor state isolation. |
| **Edge: Checksum-failed frames discarded** | artifact | PASS | `test_status_bit0_fails_checksum` and `test_bad_p1_fails_checksum` verify checksum gate rejects frames with `status & 0x01 == 1` or bad p1 reserved bits before reaching status extraction (tublemetry_display.cpp line 210 returns early). |
| **Edge: Rapid light toggle** | artifact | PASS | `test_rapid_toggle_publishes_every_change` verifies True→False→True→False sequence produces 4 publishes. On-change logic publishes every transition immediately. |

## Overall Verdict

PASS — all automatable artifact and logic checks pass (336/336 tests, ESPHome compile [SUCCESS], correct bit extraction, on-change filtering verified, dashboard card structure correct). TC-02, TC-03, TC-04 require human follow-up after OTA flash to confirm status bit positions match live VS300FL4 wire data.

## Notes

**Human follow-up required after OTA flash:**
1. Flash firmware to tublemetry (192.168.0.92)
2. Open HA → Developer Tools → States, filter `binary_sensor.tublemetry` — confirm all three entities appear
3. Compare heater/pump/light binary sensor states against physical panel indicators
4. Press light button — confirm HA state changes within ~1 second
5. Leave tub idle 60s — confirm no spurious state changes in history

**Known risk:** Status bit positions (heater=p1 bit 2, pump=p4 bit 2, light=p4 bit 1) are from kgstorm protocol analysis and have not yet been verified against live VS300FL4 wire captures. If post-flash observation shows incorrect mapping, bit positions will need adjustment. This is tracked in the S03 Summary known limitations.

**Compile evidence:** `/Users/chriskaschner/Documents/GitHub/tubtron/.venv/bin/esphome compile esphome/tublemetry.yaml` → `[SUCCESS] Took 9.85 seconds`

**Test evidence:** `uv run pytest tests/ --ignore=tests/test_ladder_capture.py` → `336 passed in 0.37s`
