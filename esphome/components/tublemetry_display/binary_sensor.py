"""Binary sensor platform for Tublemetry display decoder.

Exposes heater, pump, and light status extracted from p1/p4 status bits
of the VS300FL4 display frame.
"""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import binary_sensor
from . import TublemetryDisplay

CONF_TUBLEMETRY_ID = "tublemetry_id"
CONF_HEATER = "heater"
CONF_PUMP = "pump"
CONF_LIGHT = "light"

CONFIG_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_TUBLEMETRY_ID): cv.use_id(TublemetryDisplay),
        cv.Optional(CONF_HEATER): binary_sensor.binary_sensor_schema(
            device_class="heat",
            icon="mdi:fire",
        ),
        cv.Optional(CONF_PUMP): binary_sensor.binary_sensor_schema(
            device_class="running",
            icon="mdi:pump",
        ),
        cv.Optional(CONF_LIGHT): binary_sensor.binary_sensor_schema(
            device_class="light",
            icon="mdi:lightbulb",
        ),
    }
)


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
