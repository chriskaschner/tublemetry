"""Tests for the 2027 branch of sensor.hot_tub_expected_setpoint (ha/templates.yaml).

From 2027-01-01 MGE's TOU rate is on-peak 16-20 Mon-Fri ($0.28305), off-peak
22-04 every day ($0.09435), standard otherwise ($0.18870). The user soaks every
morning (out by ~7:30) and every evening (~8:40 is fine). The schedule:

  weekday  22:00-08:00 max   (off-peak hold heats the morning soak at half price)
           08:00-preheat     coast
           preheat-16:00     max   (start time from the thermal model, see below)
           16:00-20:00       coast (ride through the peak on stored heat)
           20:00-22:00       max   (top up after the peak: 104 by ~8:40)
  weekend  max all day       (no on-peak; overnight hold is off-peak)

Preheat start: max when the minutes left before 16:00 drop to
(max - water) / heating_rate + 20 min margin. If water or rate is unusable, a
fixed 180 min lead. Once heating, it stays on while minutes-left <= lead + 60
(this.state hysteresis), so whole-degree water readings cannot make the
setpoint chatter, and every flip is a button injection.

Renders the real Jinja template with jinja2 (the engine HA uses).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import jinja2
import pytest
import yaml

TEMPLATES_FILE = Path(__file__).parent.parent / "ha" / "templates.yaml"

MON = datetime(2027, 1, 4)   # Monday
FRI = datetime(2027, 1, 8)   # Friday
SAT = datetime(2027, 1, 9)   # Saturday
SUN = datetime(2027, 1, 10)  # Sunday

MAX, COAST, RATE = 104, 90, 0.0907


def _template() -> str:
    data = yaml.safe_load(TEMPLATES_FILE.read_text())
    for block in data["template"]:
        for sensor in block.get("sensor", []):
            if sensor.get("name") == "Hot Tub Expected Setpoint":
                return sensor["state"]
    raise AssertionError("Hot Tub Expected Setpoint not found")


def render(when: datetime, water="104.0", rate=str(RATE), prev=None, hold=None) -> int:
    values = {
        "input_number.hot_tub_max_setpoint": str(MAX),
        "input_number.hot_tub_coast_setpoint": str(COAST),
        "sensor.tublemetry_hot_tub_temperature": water,
        "sensor.hot_tub_heating_rate": rate,
    }
    if hold is not None:
        values["input_boolean.hot_tub_away_hold"] = "on"
        values["input_number.hot_tub_hold_setpoint"] = str(hold)
    ctx = {"now": lambda: when, "states": lambda e: values.get(e, "unknown")}
    if prev is not None:
        ctx["this"] = SimpleNamespace(state=str(prev))
    return int(jinja2.Environment().from_string(_template()).render(**ctx).strip())


def at(day: datetime, hh: int, mm: int = 0) -> datetime:
    return day.replace(hour=hh, minute=mm)


# --- fixed windows ------------------------------------------------------------


@pytest.mark.parametrize("hh,mm,expected", [
    (0, 0, MAX),      # off-peak overnight hold
    (3, 59, MAX),
    (4, 0, MAX),      # morning soak window, standard rate
    (7, 59, MAX),
    (8, 0, COAST),    # out of the tub by ~7:30
    (16, 0, COAST),   # on-peak: coast on stored heat
    (19, 59, COAST),
    (20, 0, MAX),     # top up after the peak
    (21, 59, MAX),
    (22, 0, MAX),     # off-peak hold
    (23, 59, MAX),
])
def test_weekday_fixed_windows(hh, mm, expected):
    assert render(at(MON, hh, mm), prev=MAX) == expected


@pytest.mark.parametrize("day", [SAT, SUN])
@pytest.mark.parametrize("hh", [0, 4, 8, 12, 16, 18, 20, 23])
def test_weekend_holds_max(day, hh):
    assert render(at(day, hh), water="100.0") == MAX


def test_friday_is_a_weekday():
    assert render(at(FRI, 17)) == COAST


def test_morning_end_ignores_the_morning_max_state():
    # At 08:00 the previous state is the morning's max; hysteresis must not
    # carry it into the midday coast.
    assert render(at(MON, 8, 0), water="103.0", prev=MAX) == COAST
    assert render(at(MON, 8, 1), water="103.0", prev=MAX) == COAST


# --- dynamic preheat ----------------------------------------------------------


def lead_minutes(water: float) -> float:
    return (MAX - water) / RATE + 20


def test_preheat_starts_when_lead_reached():
    # water 98: lead = 6 / 0.0907 + 20 = 86.2 min -> start at 16:00 - 86 = 14:34.
    assert lead_minutes(98) == pytest.approx(86.15, abs=0.01)
    assert render(at(MON, 14, 33), water="98.0", prev=COAST) == COAST
    assert render(at(MON, 14, 34), water="98.0", prev=COAST) == MAX


def test_colder_water_starts_earlier():
    # water 92: lead = 12 / 0.0907 + 20 = 152.3 min -> start at 13:28.
    assert render(at(MON, 13, 27), water="92.0", prev=COAST) == COAST
    assert render(at(MON, 13, 28), water="92.0", prev=COAST) == MAX


def test_slower_learned_rate_starts_earlier():
    # Same water, rate 0.06 F/min (a cold-weather heat-up): lead = 120 min.
    assert render(at(MON, 13, 59), water="98.0", rate="0.06", prev=COAST) == COAST
    assert render(at(MON, 14, 0), water="98.0", rate="0.06", prev=COAST) == MAX


def test_stays_on_while_heating_ahead_of_schedule():
    # Heating faster than modelled: at 15:00 water is already 103, lead 31 min,
    # 60 min left. Without hysteresis it would drop to coast, then restart.
    assert render(at(MON, 15, 0), water="103.0", prev=MAX) == MAX
    assert render(at(MON, 15, 0), water="103.0", prev=COAST) == COAST


def test_stays_on_at_target_until_the_peak():
    assert render(at(MON, 15, 30), water="104.0", prev=MAX) == MAX
    assert render(at(MON, 15, 59), water="104.0", prev=MAX) == MAX


def test_hot_water_midday_stays_coasting():
    assert render(at(MON, 12, 0), water="103.0", prev=COAST) == COAST


@pytest.mark.parametrize("water,rate", [
    ("unknown", str(RATE)),
    ("unavailable", str(RATE)),
    ("24.0", str(RATE)),      # implausible reading (the 2026-10-28 boot glitch)
    ("98.0", "unknown"),
    ("98.0", "0"),
    ("98.0", "0.52"),         # implausible rate (the pre-fix SQL value)
])
def test_unusable_inputs_fall_back_to_a_fixed_180_min_lead(water, rate):
    assert render(at(MON, 12, 59), water=water, rate=rate, prev=COAST) == COAST
    assert render(at(MON, 13, 0), water=water, rate=rate, prev=COAST) == MAX


def test_no_this_state_after_restart():
    # Right after an HA restart `this` may carry no usable state.
    assert render(at(MON, 14, 34), water="98.0") == MAX
    assert render(at(MON, 12, 0), water="98.0") == COAST


# --- holds and the year boundary ----------------------------------------------


def test_away_hold_replaces_the_2027_schedule():
    assert render(at(MON, 21), hold=95) == 95
    assert render(at(SAT, 12), hold=95) == 95


def test_switches_on_new_years_day():
    # 2026-12-31 23:00 is the old schedule's overnight coast; 2027-01-01 00:00
    # (a Friday) is the new off-peak hold.
    assert render(datetime(2026, 12, 31, 23, 0)) == COAST
    assert render(datetime(2027, 1, 1, 0, 0)) == MAX
