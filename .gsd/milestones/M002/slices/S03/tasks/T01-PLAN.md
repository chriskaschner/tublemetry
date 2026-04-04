---
estimated_steps: 87
estimated_files: 5
skills_used: []
---

# T01: Add binary sensor C++ members, extraction logic, ESPHome codegen, and YAML entries

Add heater/pump/light binary sensor support end-to-end: C++ header + implementation + ESPHome binary_sensor.py + AUTO_LOAD update + tublemetry.yaml entries. Compile verifies everything wires together.

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

## Inputs

- ``esphome/components/tublemetry_display/tublemetry_display.h` — existing header; add binary_sensor include and member declarations`
- ``esphome/components/tublemetry_display/tublemetry_display.cpp` — existing implementation; add bit extraction block after classify_display_state_() call`
- ``esphome/components/tublemetry_display/sensor.py` — pattern reference for binary_sensor.py structure`
- ``esphome/components/tublemetry_display/__init__.py` — add binary_sensor to AUTO_LOAD`
- ``esphome/tublemetry.yaml` — add binary_sensor platform entry`

## Expected Output

- ``esphome/components/tublemetry_display/tublemetry_display.h` — updated with binary_sensor include and three sensor pointers + setters + last_* tracking members`
- ``esphome/components/tublemetry_display/tublemetry_display.cpp` — updated with heater/pump/light bit extraction block after classify_display_state_() call`
- ``esphome/components/tublemetry_display/binary_sensor.py` — new file implementing the binary sensor platform`
- ``esphome/components/tublemetry_display/__init__.py` — updated with binary_sensor in AUTO_LOAD`
- ``esphome/tublemetry.yaml` — updated with tublemetry_display binary sensor entries for heater, pump, light`

## Verification

/Users/chriskaschner/Documents/GitHub/tubtron/.venv/bin/esphome compile esphome/tublemetry.yaml 2>&1 | grep -E '\[SUCCESS\]|ERROR'
