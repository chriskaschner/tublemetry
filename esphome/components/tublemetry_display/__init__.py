"""ESPHome external component for Tublemetry VS300FL4 display decoder.

Reads synchronous clock+data GPIO signals from the Balboa VS300FL4
hot tub controller and decodes the 7-segment display stream.

Registers climate, sensor, and text_sensor platforms.
"""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome import pins
from esphome.const import CONF_ID

CODEOWNERS = ["@tublemetry"]
DEPENDENCIES = []
AUTO_LOAD = ["climate", "sensor", "text_sensor"]

MULTI_CONF = False

# Namespace and class
tublemetry_display_ns = cg.esphome_ns.namespace("tublemetry_display")
TublemetryDisplay = tublemetry_display_ns.class_(
    "TublemetryDisplay", cg.Component
)

# Config keys
CONF_CLOCK_PIN = "clock_pin"
CONF_DATA_PIN = "data_pin"

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(TublemetryDisplay),
        cv.Required(CONF_CLOCK_PIN): pins.internal_gpio_input_pin_schema,
        cv.Required(CONF_DATA_PIN): pins.internal_gpio_input_pin_schema,
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)

    clock_pin = await cg.gpio_pin_expression(config[CONF_CLOCK_PIN])
    cg.add(var.set_clock_pin(clock_pin))

    data_pin = await cg.gpio_pin_expression(config[CONF_DATA_PIN])
    cg.add(var.set_data_pin(data_pin))
