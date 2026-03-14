"""Climate platform for Tubtron display decoder.

Exposes a read-only climate entity (climate.hot_tub) that reports the
current water temperature decoded from the RS-485 display stream.
"""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import climate
from esphome.const import CONF_ID

from . import TubtronDisplay, tubtron_display_ns

CONF_TUBTRON_ID = "tubtron_id"

TubtronClimate = tubtron_display_ns.class_(
    "TubtronClimate", climate.Climate, cg.Component
)

CONFIG_SCHEMA = climate.CLIMATE_SCHEMA.extend(
    {
        cv.GenerateID(): cv.declare_id(TubtronClimate),
        cv.Required(CONF_TUBTRON_ID): cv.use_id(TubtronDisplay),
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await climate.register_climate(var, config)

    parent = await cg.get_variable(config[CONF_TUBTRON_ID])
    cg.add(parent.set_climate(var))
