"""Sensor platform for Tubtron display decoder.

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

from . import TubtronDisplay

CONF_TUBTRON_ID = "tubtron_id"
CONF_DECODE_CONFIDENCE = "decode_confidence"

CONFIG_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_TUBTRON_ID): cv.use_id(TubtronDisplay),
        cv.Optional(CONF_DECODE_CONFIDENCE): sensor.sensor_schema(
            unit_of_measurement=UNIT_PERCENT,
            icon=ICON_PERCENT,
            accuracy_decimals=0,
            entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
        ),
    }
)


async def to_code(config):
    parent = await cg.get_variable(config[CONF_TUBTRON_ID])

    if conf := config.get(CONF_DECODE_CONFIDENCE):
        sens = await sensor.new_sensor(conf)
        cg.add(parent.set_decode_confidence_sensor(sens))
