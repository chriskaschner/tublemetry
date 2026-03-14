"""ESPHome external component for Tubtron VS300FL4 display decoder.

Reads dual RS-485 UARTs (Pin 5 and Pin 6) from the Balboa VS300FL4
hot tub controller and decodes the 7-segment display stream.

Registers climate, sensor, and text_sensor platforms.
"""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import uart
from esphome.const import CONF_ID

CODEOWNERS = ["@tubtron"]
DEPENDENCIES = ["uart"]
AUTO_LOAD = ["climate", "sensor", "text_sensor"]

MULTI_CONF = False

# Namespace and class
tubtron_display_ns = cg.esphome_ns.namespace("tubtron_display")
TubtronDisplay = tubtron_display_ns.class_(
    "TubtronDisplay", cg.Component
)

# Config keys
CONF_UART_PIN5 = "uart_pin5"
CONF_UART_PIN6 = "uart_pin6"

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(TubtronDisplay),
        cv.Required(CONF_UART_PIN5): cv.use_id(uart.UARTComponent),
        cv.Required(CONF_UART_PIN6): cv.use_id(uart.UARTComponent),
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)

    uart_pin5 = await cg.get_variable(config[CONF_UART_PIN5])
    cg.add(var.set_uart_pin5(uart_pin5))

    uart_pin6 = await cg.get_variable(config[CONF_UART_PIN6])
    cg.add(var.set_uart_pin6(uart_pin6))
