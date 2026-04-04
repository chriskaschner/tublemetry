# S03: Status Bit Binary Sensors

**Goal:** Expose heater, pump, and light state as HA binary sensors by extracting three bits from already-decoded frame data in process_frame_(), wiring them through ESPHome codegen, and verifying with Python bit-extraction tests + firmware compile.
**Demo:** After this: After this: heater, pump, and light status appear as binary sensors in HA. Dashboard shows new status card.

## Tasks
- [x] **T01: Added heater/pump/light binary sensors end-to-end — C++ members, bit extraction, ESPHome codegen, and YAML — compiling clean** — Add heater/pump/light binary sensor support end-to-end: C++ header + implementation + ESPHome binary_sensor.py + AUTO_LOAD update + tublemetry.yaml entries. Compile verifies everything wires together.

Steps:
1. Read `esphome/components/tublemetry_display/tublemetry_display.h` — add `#include "esphome/components/binary_sensor/binary_sensor.h"` after the text_sensor include, then add three sensor pointer members and setter methods to the protected section:
   ```cpp
   binary_sensor::BinarySensor *heater_binary_sensor_{nullptr};
   binary_sensor::BinarySensor *pump_binary_sensor_{nullptr};
   binary_sensor::BinarySensor *light_binary_sensor_{nullptr};
   // last-state tracking for publish-on-change
   int8_t last_heater_{-1};
   int8_t last_pump_{-1};
   int8_t last_light_{-1};
   ```
   And setter methods in the public section:
   ```cpp
   void set_heater_binary_sensor(binary_sensor::BinarySensor *s) { this->heater_binary_sensor_ = s; }
   void set_pump_binary_sensor(binary_sensor::BinarySensor *s) { this->pump_binary_sensor_ = s; }
   void set_light_binary_sensor(binary_sensor::BinarySensor *s) { this->light_binary_sensor_ = s; }
   ```
2. Read `esphome/components/tublemetry_display/tublemetry_display.cpp` — in `process_frame_()`, after the `this->classify_display_state_(display_str);` call, add the status bit extraction block:
   ```cpp
   // Status bits: extract p1 outside the checksum scoped block for heater
   uint8_t p1_full = (frame_bits >> 17) & 0x7F;
   bool heater_on = (p1_full >> 2) & 0x01;  // p1 bit 2
   bool pump_on   = (status >> 2) & 0x01;   // p4 bit 2
   bool light_on  = (status >> 1) & 0x01;   // p4 bit 1
   if (static_cast<int8_t>(heater_on) != this->last_heater_) {
     this->last_heater_ = static_cast<int8_t>(heater_on);
     if (this->heater_binary_sensor_ != nullptr) this->heater_binary_sensor_->publish_state(heater_on);
   }
   if (static_cast<int8_t>(pump_on) != this->last_pump_) {
     this->last_pump_ = static_cast<int8_t>(pump_on);
     if (this->pump_binary_sensor_ != nullptr) this->pump_binary_sensor_->publish_state(pump_on);
   }
   if (static_cast<int8_t>(light_on) != this->last_light_) {
     this->last_light_ = static_cast<int8_t>(light_on);
     if (this->light_binary_sensor_ != nullptr) this->light_binary_sensor_->publish_state(light_on);
   }
   ```
   Note: `status` is already in scope from the top of `process_frame_()`. `p1_full` re-extracts digit_bytes[0] — this is intentional because the checksum scoped block's `p1` variable is out of scope here.
3. Create `esphome/components/tublemetry_display/binary_sensor.py` following the sensor.py pattern:
   ```python
   import esphome.codegen as cg
   import esphome.config_validation as cv
   from esphome.components import binary_sensor
   from . import TublemetryDisplay

   CONF_TUBLEMETRY_ID = "tublemetry_id"
   CONF_HEATER = "heater"
   CONF_PUMP = "pump"
   CONF_LIGHT = "light"

   CONFIG_SCHEMA = cv.Schema({
       cv.Required(CONF_TUBLEMETRY_ID): cv.use_id(TublemetryDisplay),
       cv.Optional(CONF_HEATER): binary_sensor.binary_sensor_schema(
           device_class="heat", icon="mdi:fire"
       ),
       cv.Optional(CONF_PUMP): binary_sensor.binary_sensor_schema(
           device_class="running", icon="mdi:pump"
       ),
       cv.Optional(CONF_LIGHT): binary_sensor.binary_sensor_schema(
           device_class="light", icon="mdi:lightbulb"
       ),
   })

   async def to_code(config):
       parent = await cg.get_variable(config[CONF_TUBLEMETRY_ID])
       if conf := config.get(CONF_HEATER):
           sens = await binary_sensor.new_binary_sensor(conf)
           cg.add(parent.set_heater_binary_sensor(sens))
       if conf := config.get(CONF_PUMP):
           sens = await binary_sensor.new_binary_sensor(conf)
           cg.add(parent.set_pump_binary_sensor(sens))
       if conf := config.get(CONF_LIGHT):
           sens = await binary_sensor.new_binary_sensor(conf)
           cg.add(parent.set_light_binary_sensor(sens))
   ```
4. Edit `esphome/components/tublemetry_display/__init__.py` — add `"binary_sensor"` to the AUTO_LOAD list: `AUTO_LOAD = ["sensor", "text_sensor", "number", "binary_sensor"]`
5. Edit `esphome/tublemetry.yaml` — add under the `binary_sensor:` section after the existing `status` platform entry:
   ```yaml
     - platform: tublemetry_display
       tublemetry_id: hot_tub_display
       heater:
         name: "Hot Tub Heater"
       pump:
         name: "Hot Tub Pump"
       light:
         name: "Hot Tub Light"
   ```
6. Symlink secrets.yaml if not already present: `test -f esphome/secrets.yaml || ln -s ../../secrets.yaml esphome/secrets.yaml`
7. Run compile: `/Users/chriskaschner/Documents/GitHub/tubtron/.venv/bin/esphome compile esphome/tublemetry.yaml`
  - Estimate: 1h
  - Files: esphome/components/tublemetry_display/tublemetry_display.h, esphome/components/tublemetry_display/tublemetry_display.cpp, esphome/components/tublemetry_display/binary_sensor.py, esphome/components/tublemetry_display/__init__.py, esphome/tublemetry.yaml
  - Verify: /Users/chriskaschner/Documents/GitHub/tubtron/.venv/bin/esphome compile esphome/tublemetry.yaml 2>&1 | grep -E '\[SUCCESS\]|ERROR'
- [x] **T02: Added 36 new tests covering heater/pump/light bit extraction, all 8 status combinations, checksum compatibility, and publish-on-change; extended YAML entity test; appended status card to dashboard — 336 passed, 0 failures** — Add tests/test_status_bits.py with Python mirrors of the C++ bit extraction logic. Extend test_esphome_yaml.py with binary sensor entity checks. Add a status card to ha/dashboard.yaml.

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
  - Estimate: 45m
  - Files: tests/test_status_bits.py, tests/test_esphome_yaml.py, ha/dashboard.yaml
  - Verify: uv run pytest tests/ --ignore=tests/test_ladder_capture.py -v 2>&1 | tail -5
