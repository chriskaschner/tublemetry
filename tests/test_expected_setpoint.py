"""Tests for sensor.hot_tub_expected_setpoint (ha/templates.yaml).

This renders the actual Jinja template with jinja2 (the same engine HA uses) for
representative times, so it verifies the real schedule math -- not just that the
right strings appear in the YAML.
"""

from datetime import datetime
from pathlib import Path

import jinja2
import pytest
import yaml

TEMPLATES_FILE = Path(__file__).parent.parent / "ha" / "templates.yaml"

# 2026-07-15 is a Wednesday; 2026-07-18 is a Saturday.
WED = datetime(2026, 7, 15)
SAT = datetime(2026, 7, 18)


def _expected_setpoint_template():
    data = yaml.safe_load(TEMPLATES_FILE.read_text())
    for block in data["template"]:
        for sensor in block.get("sensor", []):
            if sensor.get("name") == "Hot Tub Expected Setpoint":
                return sensor["state"]
    raise AssertionError("Hot Tub Expected Setpoint sensor not found in templates.yaml")


_ENV = jinja2.Environment()


def render(when: datetime, maxsp: int, coast: int) -> int:
    tmpl = _ENV.from_string(_expected_setpoint_template())

    def states(entity):
        return {
            "input_number.hot_tub_max_setpoint": str(maxsp),
            "input_number.hot_tub_coast_setpoint": str(coast),
        }.get(entity, "unknown")

    out = tmpl.render(now=lambda: when, states=states).strip()
    return int(out)


def at(base: datetime, hh: int, mm: int) -> datetime:
    return base.replace(hour=hh, minute=mm)


# --------------------------------------------------------------------------- #
# Weekday schedule (max=104, coast=96 -> evening preheat = 102)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("hh,mm,expected", [
    (3, 0, 96),     # before morning preheat -> coast
    (4, 30, 104),   # morning preheat boundary -> max
    (9, 59, 104),   # still off-peak morning -> max
    (10, 0, 96),    # on-peak begins -> coast floor
    (12, 0, 96),    # mid on-peak -> coast
    (17, 29, 96),   # just before evening preheat -> coast
    (17, 30, 102),  # evening preheat boundary -> max-2
    (18, 59, 102),  # evening preheat -> max-2
    (19, 0, 104),   # evening full -> max
    (21, 59, 104),  # late evening -> max
    (22, 0, 96),    # night coast boundary -> coast
    (23, 30, 96),   # overnight -> coast
])
def test_weekday_schedule(hh, mm, expected):
    assert render(at(WED, hh, mm), 104, 96) == expected


# --------------------------------------------------------------------------- #
# Weekend schedule (hold max all day, coast overnight)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("hh,mm,expected", [
    (4, 59, 96),    # before morning -> coast
    (5, 0, 104),    # weekend preheat boundary -> max
    (12, 0, 104),   # midday hold -> max
    (21, 59, 104),  # evening -> max
    (22, 0, 96),    # night coast -> coast
    (2, 0, 96),     # overnight -> coast
])
def test_weekend_schedule(hh, mm, expected):
    assert render(at(SAT, hh, mm), 104, 96) == expected


# --------------------------------------------------------------------------- #
# Seasonal sliders actually change the output
# --------------------------------------------------------------------------- #
def test_summer_max_lowers_comfort_temp():
    # Summer: max=101 -> evening preheat = 99, full = 101; coast unchanged.
    assert render(at(WED, 19, 0), 101, 96) == 101
    assert render(at(WED, 17, 30), 101, 96) == 99
    assert render(at(WED, 12, 0), 101, 96) == 96


def test_coast_slider_changes_floor():
    assert render(at(WED, 12, 0), 104, 90) == 90
    assert render(at(WED, 23, 0), 104, 90) == 90


def test_defaults_when_sliders_unavailable():
    # If the input_numbers are unavailable, template falls back to 104/96.
    tmpl = _ENV.from_string(_expected_setpoint_template())
    out = tmpl.render(now=lambda: at(WED, 12, 0), states=lambda e: "unknown").strip()
    assert int(out) == 96  # on-peak coast default
    out = tmpl.render(now=lambda: at(WED, 19, 0), states=lambda e: "unknown").strip()
    assert int(out) == 104  # evening full default
