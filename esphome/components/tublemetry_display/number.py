"""Number platform for Tublemetry display decoder.

Exposes the setpoint number entity for HA-driven temperature control.
Writing a value from HA calls ButtonInjector::request_temperature() directly.
No unit conversion: values are plain integer degF.
"""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import number
from esphome.core import ID

from . import TublemetryDisplay, tublemetry_display_ns, INJECTOR_ID, ButtonInjector

CONF_TUBLEMETRY_ID = "tublemetry_id"
CONF_SETPOINT = "setpoint"

TublemetrySetpoint = tublemetry_display_ns.class_(
    "TublemetrySetpoint", number.Number
)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_TUBLEMETRY_ID): cv.use_id(TublemetryDisplay),
        cv.Optional(CONF_SETPOINT): number.number_schema(
            TublemetrySetpoint,
            icon="mdi:thermometer",
        ),
    }
)


async def to_code(config):
    parent = await cg.get_variable(config[CONF_TUBLEMETRY_ID])

    if conf := config.get(CONF_SETPOINT):
        var = await number.new_number(
            conf,
            min_value=80.0,
            max_value=104.0,
            step=1.0,
        )
        injector_id = ID(INJECTOR_ID, is_declaration=False, type=ButtonInjector)
        try:
            injector = await cg.get_variable(injector_id)
            cg.add(var.set_button_injector(injector))
        except Exception:
            pass
        cg.add(parent.set_setpoint_number(var))
