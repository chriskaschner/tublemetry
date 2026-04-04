---
estimated_steps: 28
estimated_files: 3
skills_used: []
---

# T02: Write Python bit-extraction tests, YAML entity tests, and update dashboard

Add tests/test_status_bits.py with Python mirrors of the C++ bit extraction logic. Extend test_esphome_yaml.py with binary sensor entity checks. Add a status card to ha/dashboard.yaml.

Steps:
1. Create `tests/test_status_bits.py` using the `digits_to_frame` helper from `test_mock_frames.py`. Import it directly: `from test_mock_frames import digits_to_frame, frame_to_digits`. Test the three bit extraction functions as Python equivalents of the C++ logic:
   - Heater: `(p1 >> 2) & 0x01` — bit 2 of the hundreds digit byte
   - Pump: `(status >> 2) & 0x01` — bit 2 of the 3-bit status
   - Light: `(status >> 1) & 0x01` — bit 1 of the 3-bit status
   Tests must include:
   - `TestStatusBitExtraction`: verify heater=1 when p1 bit 2 set; heater=0 when clear; pump=1 when status bit 2 set; pump=0 when clear; light=1 when status bit 1 set; light=0 when clear
   - `TestStatusBitCombinations`: all 8 combinations of heater/pump/light (0-7); verify each extracts cleanly
   - `TestChecksumCompatibility`: frames with status bits set for pump/light (status=0b100, 0b010, 0b110) still pass the checksum gate (bit 0 = 0); status=0b001 (pump/light bit 0 set = bit 0 of status) fails checksum — this is the sentinel
   - `TestPublishOnChange`: Python-mirror of the change-detection logic — verify that the same value twice doesn't re-publish (simulate with last_state variable)
   Use `digits_to_frame(d1, d2, d3, status)` to construct frames with specific heater/pump/light bit patterns. For heater, use p1=0x04 (bit 2 set) or p1=0x00 (bit 2 clear) — both clear CHECKSUM_MASK=0x4B since 0x04 & 0x4B = 0x00.
2. Read `tests/test_esphome_yaml.py` — add to `TestEsphomeYaml` a new test `test_tublemetry_binary_sensors_present` that verifies the binary_sensor section contains a `tublemetry_display` platform entry with heater, pump, and light keys.
3. Read `ha/dashboard.yaml` — append a new status card at the end:
   ```yaml
   ---
   # Card 6: Status
   type: entities
   title: Hot Tub Status
   entities:
     - entity: binary_sensor.tublemetry_hot_tub_heater
       name: Heater
     - entity: binary_sensor.tublemetry_hot_tub_pump
       name: Pump
     - entity: binary_sensor.tublemetry_hot_tub_light
       name: Light
   ```
4. Run full pytest suite to confirm zero regressions.

## Inputs

- ``tests/test_mock_frames.py` — provides digits_to_frame and frame_to_digits helpers`
- ``tests/test_esphome_yaml.py` — extend with binary sensor entity check`
- ``esphome/tublemetry.yaml` — source of truth for entity names (produced by T01)`
- ``ha/dashboard.yaml` — append status card`

## Expected Output

- ``tests/test_status_bits.py` — new file with 4 test classes covering bit extraction, all combinations, checksum compatibility, and publish-on-change simulation`
- ``tests/test_esphome_yaml.py` — updated with tublemetry_display binary sensor presence test`
- ``ha/dashboard.yaml` — updated with status card for heater/pump/light`

## Verification

uv run pytest tests/ --ignore=tests/test_ladder_capture.py -v 2>&1 | tail -5
