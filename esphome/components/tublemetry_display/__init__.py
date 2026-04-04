"""ESPHome external component for Tublemetry VS300FL4 display decoder.

Reads synchronous clock+data GPIO signals from the Balboa VS300FL4
hot tub controller and decodes the 7-segment display stream.

Optionally controls temperature via photorelay button injection.

Registers climate, sensor, and text_sensor platforms.
"""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome import pins
from esphome.const import CONF_ID
from esphome.core import ID

CODEOWNERS = ["@tublemetry"]
DEPENDENCIES = []
AUTO_LOAD = ["sensor", "text_sensor", "number", "binary_sensor"]

MULTI_CONF = False

# Namespace and class
tublemetry_display_ns = cg.esphome_ns.namespace("tublemetry_display")
TublemetryDisplay = tublemetry_display_ns.class_(
    "TublemetryDisplay", cg.Component
)
ButtonInjector = tublemetry_display_ns.class_("ButtonInjector")

# Config keys
CONF_CLOCK_PIN = "clock_pin"
CONF_DATA_PIN = "data_pin"
CONF_TEMP_UP_PIN = "temp_up_pin"
CONF_TEMP_DOWN_PIN = "temp_down_pin"
CONF_PRESS_DURATION_MS = "press_duration_ms"
CONF_INTER_PRESS_DELAY_MS = "inter_press_delay_ms"
CONF_VERIFY_TIMEOUT_MS = "verify_timeout_ms"
CONF_COOLDOWN_MS = "cooldown_ms"

# Shared injector variable ID (used by climate.py to wire the injector)
INJECTOR_ID = "tublemetry_button_injector"

CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(TublemetryDisplay),
            cv.Required(CONF_CLOCK_PIN): pins.internal_gpio_input_pin_schema,
            cv.Required(CONF_DATA_PIN): pins.internal_gpio_input_pin_schema,
            # Button injection pins (optional — omit for read-only mode)
            cv.Optional(CONF_TEMP_UP_PIN): pins.gpio_output_pin_schema,
            cv.Optional(CONF_TEMP_DOWN_PIN): pins.gpio_output_pin_schema,
            # Timing configuration (optional, sensible defaults)
            cv.Optional(CONF_PRESS_DURATION_MS, default=200): cv.positive_int,
            cv.Optional(CONF_INTER_PRESS_DELAY_MS, default=300): cv.positive_int,
            cv.Optional(CONF_VERIFY_TIMEOUT_MS, default=10000): cv.positive_int,
            cv.Optional(CONF_COOLDOWN_MS, default=1000): cv.positive_int,
        }
    ).extend(cv.COMPONENT_SCHEMA),
    cv.has_none_or_all_keys(CONF_TEMP_UP_PIN, CONF_TEMP_DOWN_PIN),
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)

    clock_pin = await cg.gpio_pin_expression(config[CONF_CLOCK_PIN])
    cg.add(var.set_clock_pin(clock_pin))

    data_pin = await cg.gpio_pin_expression(config[CONF_DATA_PIN])
    cg.add(var.set_data_pin(data_pin))

    # Button injection (optional)
    if CONF_TEMP_UP_PIN in config:
        injector_id = ID(INJECTOR_ID, is_declaration=True, type=ButtonInjector)
        injector = cg.new_Pvariable(injector_id)

        up_pin = await cg.gpio_pin_expression(config[CONF_TEMP_UP_PIN])
        cg.add(injector.set_temp_up_pin(up_pin))

        down_pin = await cg.gpio_pin_expression(config[CONF_TEMP_DOWN_PIN])
        cg.add(injector.set_temp_down_pin(down_pin))

        cg.add(injector.set_press_duration_ms(config[CONF_PRESS_DURATION_MS]))
        cg.add(injector.set_inter_press_delay_ms(config[CONF_INTER_PRESS_DELAY_MS]))
        cg.add(injector.set_verify_timeout_ms(config[CONF_VERIFY_TIMEOUT_MS]))
        cg.add(injector.set_cooldown_ms(config[CONF_COOLDOWN_MS]))

        cg.add(var.set_button_injector(injector))
