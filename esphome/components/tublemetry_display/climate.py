"""Climate platform for Tublemetry display decoder.

Exposes a climate entity (climate.hot_tub) that reports the current
water temperature decoded from the RS-485 display stream and accepts
target temperature setpoints via button injection.
"""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import climate
from esphome.const import CONF_ID
from esphome.core import ID, coroutine_with_priority

from . import TublemetryDisplay, ButtonInjector, tublemetry_display_ns, INJECTOR_ID

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

    # Wire button injector into climate if it was created by __init__.py
    injector_id = ID(INJECTOR_ID, is_declaration=False, type=ButtonInjector)
    try:
        injector = await cg.get_variable(injector_id)
        cg.add(var.set_button_injector(injector))
    except KeyError:
        pass  # No button injection configured — read-only mode
