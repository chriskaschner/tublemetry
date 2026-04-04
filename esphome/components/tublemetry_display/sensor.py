"""Sensor platform for Tublemetry display decoder.

Exposes the decode_confidence numeric sensor (entity_category: diagnostic).
"""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import sensor
from esphome.const import (
    CONF_ID,
    ENTITY_CATEGORY_DIAGNOSTIC,
    UNIT_PERCENT,
    ICON_PERCENT,
)


from . import TublemetryDisplay

CONF_TUBLEMETRY_ID = "tublemetry_id"
CONF_DECODE_CONFIDENCE = "decode_confidence"
CONF_TEMPERATURE = "temperature"

CONFIG_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_TUBLEMETRY_ID): cv.use_id(TublemetryDisplay),
        cv.Optional(CONF_DECODE_CONFIDENCE): sensor.sensor_schema(
            unit_of_measurement=UNIT_PERCENT,
            icon=ICON_PERCENT,
            accuracy_decimals=0,
            entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
        ),
        cv.Optional(CONF_TEMPERATURE): sensor.sensor_schema(
            icon="mdi:thermometer",
            accuracy_decimals=0,
        ),
    }
)


async def to_code(config):
    parent = await cg.get_variable(config[CONF_TUBLEMETRY_ID])

    if conf := config.get(CONF_DECODE_CONFIDENCE):
        sens = await sensor.new_sensor(conf)
        cg.add(parent.set_decode_confidence_sensor(sens))

    if conf := config.get(CONF_TEMPERATURE):
        sens = await sensor.new_sensor(conf)
        cg.add(parent.set_temperature_sensor(sens))
