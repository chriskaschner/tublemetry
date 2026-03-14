"""Text sensor platform for Tubtron display decoder.

Exposes diagnostic text sensors:
  - display_string: assembled display string (e.g. "104", "OH", "--")
  - raw_hex: raw hex bytes (e.g. "FE 06 70 30 00 06 70 00")
  - display_state: display state classification (e.g. "temperature", "OH")
  - digit_values: per-digit breakdown (e.g. "8|?|7|1| |?|7| ")
  - last_update: ISO 8601 timestamp of last display frame processed
"""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import text_sensor
from esphome.const import ENTITY_CATEGORY_DIAGNOSTIC

from . import TubtronDisplay

CONF_TUBTRON_ID = "tubtron_id"
CONF_DISPLAY_STRING = "display_string"
CONF_RAW_HEX = "raw_hex"
CONF_DISPLAY_STATE = "display_state"
CONF_DIGIT_VALUES = "digit_values"
CONF_LAST_UPDATE = "last_update"

CONFIG_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_TUBTRON_ID): cv.use_id(TubtronDisplay),
        cv.Optional(CONF_DISPLAY_STRING): text_sensor.text_sensor_schema(
            icon="mdi:format-text",
            entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
        ),
        cv.Optional(CONF_RAW_HEX): text_sensor.text_sensor_schema(
            icon="mdi:hexadecimal",
            entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
        ),
        cv.Optional(CONF_DISPLAY_STATE): text_sensor.text_sensor_schema(
            icon="mdi:state-machine",
            entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
        ),
        cv.Optional(CONF_DIGIT_VALUES): text_sensor.text_sensor_schema(
            icon="mdi:numeric",
            entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
        ),
        cv.Optional(CONF_LAST_UPDATE): text_sensor.text_sensor_schema(
            icon="mdi:clock-outline",
            entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
        ),
    }
)


async def to_code(config):
    parent = await cg.get_variable(config[CONF_TUBTRON_ID])

    if conf := config.get(CONF_DISPLAY_STRING):
        sens = await text_sensor.new_text_sensor(conf)
        cg.add(parent.set_display_string_sensor(sens))

    if conf := config.get(CONF_RAW_HEX):
        sens = await text_sensor.new_text_sensor(conf)
        cg.add(parent.set_raw_hex_sensor(sens))

    if conf := config.get(CONF_DISPLAY_STATE):
        sens = await text_sensor.new_text_sensor(conf)
        cg.add(parent.set_display_state_sensor(sens))

    if conf := config.get(CONF_DIGIT_VALUES):
        sens = await text_sensor.new_text_sensor(conf)
        cg.add(parent.set_digit_values_sensor(sens))

    if conf := config.get(CONF_LAST_UPDATE):
        sens = await text_sensor.new_text_sensor(conf)
        cg.add(parent.set_last_update_sensor(sens))
