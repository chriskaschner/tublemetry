"""Tests for ha/electricity_rate.yaml -- MGE time-of-use price sensors.

The import price follows MGE Schedule Rg-2A (effective 2026-01-01) through
2026-12-31, then the new three-period TOU rate from 2027-01-01. Under net
metering exports are credited at the same $/kWh as imports, so the export
sensor mirrors the import one. Both feed the Energy dashboard's cost tracking.

Renders the real Jinja templates with jinja2 (HA's engine) at chosen times.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import jinja2
import pytest

from ha_yaml import load_ha_yaml

PKG_FILE = Path(__file__).parent.parent / "ha" / "electricity_rate.yaml"

# Rg-2A (2026): distribution 0.06255 + base energy 0.07731 every hour, plus a
# weekday on-peak adder (summer = Jun 1 - Sep 30).
BASE_2026 = 0.13986
WINTER_P1, WINTER_P2, WINTER_P3 = 0.23632, 0.23341, 0.23781  # 10-13, 13-18, 18-21
SUMMER_P1, SUMMER_P2, SUMMER_P3 = 0.23656, 0.24639, 0.24092

# 2027 TOU: on-peak 16-20 Mon-Fri, off-peak 22-04 every day, standard otherwise.
ON_PEAK_2027, STANDARD_2027, OFF_PEAK_2027 = 0.28305, 0.18870, 0.09435


@pytest.fixture(scope="module")
def pkg():
    return load_ha_yaml(PKG_FILE)


def _sensor(pkg, unique_id: str) -> dict:
    for block in pkg["template"]:
        for s in block.get("sensor", []):
            if s.get("unique_id") == unique_id:
                return s
    raise AssertionError(f"{unique_id} not found")


def price(pkg, when: datetime) -> float:
    tmpl = jinja2.Environment().from_string(_sensor(pkg, "electricity_import_price")["state"])
    return float(tmpl.render(now=lambda: when).strip())


# --- structure ----------------------------------------------------------------


def test_sensors_have_energy_dashboard_units(pkg):
    for uid in ("electricity_import_price", "electricity_export_price"):
        assert _sensor(pkg, uid)["unit_of_measurement"] == "USD/kWh"


def test_export_price_mirrors_import(pkg):
    state = _sensor(pkg, "electricity_export_price")["state"]
    assert "sensor.electricity_import_price" in state


def test_export_price_renders_the_import_value(pkg):
    tmpl = jinja2.Environment().from_string(_sensor(pkg, "electricity_export_price")["state"])
    states = {"sensor.electricity_import_price": "0.28305"}
    assert tmpl.render(states=lambda e: states.get(e, "unknown")).strip() == "0.28305"


# --- 2026: Schedule Rg-2A -----------------------------------------------------

WED_NOV = datetime(2026, 11, 18)  # Wednesday, winter
WED_JUL = datetime(2026, 7, 15)   # Wednesday, summer


@pytest.mark.parametrize("hh,mm,expected", [
    (0, 0, BASE_2026),
    (9, 59, BASE_2026),
    (10, 0, WINTER_P1),
    (12, 59, WINTER_P1),
    (13, 0, WINTER_P2),
    (17, 59, WINTER_P2),
    (18, 0, WINTER_P3),
    (20, 59, WINTER_P3),
    (21, 0, BASE_2026),
    (23, 59, BASE_2026),
])
def test_2026_winter_weekday(pkg, hh, mm, expected):
    assert price(pkg, WED_NOV.replace(hour=hh, minute=mm)) == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize("hh,expected", [(11, SUMMER_P1), (14, SUMMER_P2), (19, SUMMER_P3), (22, BASE_2026)])
def test_2026_summer_weekday(pkg, hh, expected):
    assert price(pkg, WED_JUL.replace(hour=hh)) == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize("day", [
    datetime(2026, 6, 1),    # first summer day (Monday)
    datetime(2026, 9, 30),   # last summer day (Wednesday)
])
def test_2026_summer_bounds(pkg, day):
    assert price(pkg, day.replace(hour=14)) == pytest.approx(SUMMER_P2, abs=1e-6)


def test_2026_october_is_winter(pkg):
    assert price(pkg, datetime(2026, 10, 1, 14)) == pytest.approx(WINTER_P2, abs=1e-6)


@pytest.mark.parametrize("day", [
    datetime(2026, 11, 21),  # Saturday
    datetime(2026, 11, 22),  # Sunday
])
def test_2026_weekend_has_no_peak(pkg, day):
    for hh in (11, 15, 19):
        assert price(pkg, day.replace(hour=hh)) == pytest.approx(BASE_2026, abs=1e-6)


@pytest.mark.parametrize("day", [
    datetime(2026, 1, 1),    # New Year's Day (Thursday)
    datetime(2026, 5, 25),   # Memorial Day (last Monday of May)
    datetime(2026, 9, 7),    # Labor Day (first Monday of September)
    datetime(2026, 11, 26),  # Thanksgiving (fourth Thursday of November)
    datetime(2026, 12, 25),  # Christmas (Friday)
])
def test_2026_holidays_have_no_peak(pkg, day):
    assert price(pkg, day.replace(hour=15)) == pytest.approx(BASE_2026, abs=1e-6)


@pytest.mark.parametrize("day", [
    datetime(2026, 5, 18),   # Monday a week before Memorial Day
    datetime(2026, 9, 14),   # second Monday of September
    datetime(2026, 11, 19),  # third Thursday of November
])
def test_2026_near_holidays_still_peak(pkg, day):
    assert price(pkg, day.replace(hour=15)) > BASE_2026


# --- 2027: new TOU ------------------------------------------------------------

MON_2027 = datetime(2027, 1, 4)
SAT_2027 = datetime(2027, 1, 2)


@pytest.mark.parametrize("hh,mm,expected", [
    (0, 0, OFF_PEAK_2027),
    (3, 59, OFF_PEAK_2027),
    (4, 0, STANDARD_2027),
    (15, 59, STANDARD_2027),
    (16, 0, ON_PEAK_2027),
    (19, 59, ON_PEAK_2027),
    (20, 0, STANDARD_2027),
    (21, 59, STANDARD_2027),
    (22, 0, OFF_PEAK_2027),
    (23, 59, OFF_PEAK_2027),
])
def test_2027_weekday(pkg, hh, mm, expected):
    assert price(pkg, MON_2027.replace(hour=hh, minute=mm)) == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize("hh,expected", [(3, OFF_PEAK_2027), (12, STANDARD_2027),
                                         (17, STANDARD_2027), (23, OFF_PEAK_2027)])
def test_2027_weekend(pkg, hh, expected):
    assert price(pkg, SAT_2027.replace(hour=hh)) == pytest.approx(expected, abs=1e-6)


def test_switchover_at_new_year(pkg):
    assert price(pkg, datetime(2026, 12, 31, 23, 59)) == pytest.approx(BASE_2026, abs=1e-6)
    assert price(pkg, datetime(2027, 1, 1, 0, 0)) == pytest.approx(OFF_PEAK_2027, abs=1e-6)
