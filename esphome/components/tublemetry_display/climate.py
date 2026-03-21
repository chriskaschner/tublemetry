"""Climate platform for Tublemetry display decoder.

Exposes a read-only climate entity (climate.hot_tub) that reports the
current water temperature decoded from the RS-485 display stream.
"""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import climate
from esphome.const import CONF_ID

from . import TublemetryDisplay, tublemetry_display_ns

CONF_TUBLEMETRY_ID = "tublemetry_id"

TublemetryClimate = tublemetry_display_ns.class_(
    "TublemetryClimate", climate.Climate, cg.Component
)

CONFIG_SCHEMA = climate.climate_schema(TublemetryClimate).extend(
    {
        cv.Required(CONF_TUBLEMETRY_ID): cv.use_id(TublemetryDisplay),
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await climate.register_climate(var, config)

    parent = await cg.get_variable(config[CONF_TUBLEMETRY_ID])
    cg.add(parent.set_climate(var))
