"""Tests for ha/thermal_model.yaml -- the SQL heating / cooling rate sensors.

WHY THIS EXISTS (2026-11-07): the thermal model had NEVER produced a value.
Both SQL sensors carried `scan_interval`, which the SQL integration's YAML
schema rejects, so HA failed the whole `sql:` setup at boot:

    Invalid config for 'sql' at packages/thermal_model.yaml, line 12:
    'scan_interval' is an invalid option for 'sql'

sensor.hot_tub_heating_rate / _cooling_rate never existed, the preheat
sensors read 0 / "No rate data yet", and nothing noticed. No test covered it.

Two layers:
1. The config only uses keys HA's SQL YAML schema accepts.
2. The queries are run against an in-memory SQLite copy of the recorder schema
   (states_meta + states) seeded with a known heat-up and cool-down, so the
   rates they return are checked, not just their syntax.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from ha_yaml import load_ha_yaml

PKG_FILE = Path(__file__).parent.parent / "ha" / "thermal_model.yaml"

# Options accepted per entry under the top-level `sql:` key (HA SQL integration,
# YAML schema). scan_interval is NOT among them -- see the module docstring.
SQL_YAML_KEYS = {
    "name", "query", "column", "unique_id", "db_url", "unit_of_measurement",
    "value_template", "device_class", "state_class", "icon", "picture",
    "availability",
}

WATER = "sensor.tublemetry_hot_tub_temperature"
SETPOINT = "number.tublemetry_hot_tub_setpoint"
HEATER = "binary_sensor.tublemetry_hot_tub_heater"


@pytest.fixture(scope="module")
def pkg():
    return load_ha_yaml(PKG_FILE)


def _sql(pkg, name: str) -> dict:
    return next(s for s in pkg["sql"] if s["name"] == name)


# --- 1. config schema --------------------------------------------------------


def test_sql_entries_use_only_schema_keys(pkg):
    for entry in pkg["sql"]:
        extra = set(entry) - SQL_YAML_KEYS
        assert not extra, f"{entry['name']}: HA rejects {sorted(extra)}; one bad key fails ALL sql sensors"


def test_sql_entries_have_unique_ids(pkg):
    ids = [e.get("unique_id") for e in pkg["sql"]]
    assert all(ids) and len(set(ids)) == len(ids)


def test_sql_uses_the_recorder_database(pkg):
    # Without db_url the SQL integration reuses the recorder's own engine, so a
    # move to another recorder backend cannot silently point this at a stale file.
    for entry in pkg["sql"]:
        assert "db_url" not in entry


def test_queries_read_the_fixed_firmware_sensor(pkg):
    # Since firmware 0.3.1 (2026-11-07) this sensor steps every degree, including
    # below 100F with the heater on. See tests/test_frame_decode.py.
    for name in ("Hot Tub Heating Rate", "Hot Tub Cooling Rate"):
        assert f"'{WATER}'" in _sql(pkg, name)["query"]


# --- 2. queries against a recorder-shaped database ---------------------------


@pytest.fixture
def db():
    con = sqlite3.connect(":memory:")
    con.executescript(
        """
        CREATE TABLE states_meta (metadata_id INTEGER PRIMARY KEY, entity_id TEXT);
        CREATE TABLE states (state_id INTEGER PRIMARY KEY, metadata_id INTEGER,
                             state TEXT, last_updated_ts REAL);
        """
    )
    for i, eid in enumerate((WATER, SETPOINT, HEATER), start=1):
        con.execute("INSERT INTO states_meta VALUES (?, ?)", (i, eid))
    yield con
    con.close()


def _put(con, entity_id: str, points: list[tuple[float, str]]) -> None:
    (mid,) = con.execute("SELECT metadata_id FROM states_meta WHERE entity_id = ?", (entity_id,)).fetchone()
    con.executemany("INSERT INTO states (metadata_id, state, last_updated_ts) VALUES (?, ?, ?)",
                    [(mid, s, ts) for ts, s in points])


def _run(con, pkg, name: str):
    entry = _sql(pkg, name)
    cur = con.execute(entry["query"])
    cols = [d[0] for d in cur.description]
    row = cur.fetchone()
    return None if row is None else row[cols.index(entry["column"])]


def test_heating_rate_from_a_real_shaped_heat_up(db, pkg):
    # 2026-11-07 05:00: raise 90 -> 104 with water at 97, ~7.5 min/F, reaching
    # 103 (target - 1) after 45 min. The query measures the time to target - 1,
    # so the degrees it measured are 103 - 97 = 6: 6 / 45 = 0.1333 F/min.
    t0 = time.time() - 6 * 3600
    _put(db, SETPOINT, [(t0 - 3600, "90.0"), (t0, "104.0")])
    _put(db, WATER, [(t0 - 600, "97.0")] + [(t0 + m * 60, f"{v}.0")
                                          for m, v in ((8, 98), (15, 99), (23, 100), (30, 101), (38, 102), (45, 103))])
    assert _run(db, pkg, "Hot Tub Heating Rate") == pytest.approx(0.1333, abs=0.001)


def test_heating_rate_ignores_drops_and_unreached_raises(db, pkg):
    t0 = time.time() - 6 * 3600
    _put(db, SETPOINT, [(t0 - 3600, "104.0"), (t0, "90.0"), (t0 + 600, "104.0")])
    _put(db, WATER, [(t0 - 600, "97.0")])  # never reaches 103
    assert _run(db, pkg, "Hot Tub Heating Rate") is None


def test_cooling_rate_from_a_heater_off_window(db, pkg):
    # Heater off for 6 h while the water coasts 105 -> 101: 4 / 6 = 0.67 F/hr.
    t0 = time.time() - 12 * 3600
    _put(db, HEATER, [(t0 - 1800, "on"), (t0, "off"), (t0 + 6 * 3600, "on")])
    _put(db, WATER, [(t0 + 60, "105.0"), (t0 + 2 * 3600, "104.0"), (t0 + 3.5 * 3600, "103.0"),
                     (t0 + 5 * 3600, "102.0"), (t0 + 6 * 3600 - 60, "101.0")])
    assert _run(db, pkg, "Hot Tub Cooling Rate") == pytest.approx(0.67, abs=0.01)


def test_cooling_rate_skips_short_off_windows(db, pkg):
    t0 = time.time() - 12 * 3600
    _put(db, HEATER, [(t0, "off"), (t0 + 3600, "on")])  # 1 h < the 2 h minimum
    _put(db, WATER, [(t0 + 60, "105.0"), (t0 + 3500, "104.0")])
    assert _run(db, pkg, "Hot Tub Cooling Rate") is None


def test_heating_rate_ignores_one_degree_raises(db, pkg):
    # 102 -> 104 with water at 102: only 1 degree (102 -> 103) is measured, and
    # with whole-degree readings that is mostly noise (real 102 may be 102.9).
    # Live data had these at 0.31-0.66 F/min, 2-5x the real rate.
    t0 = time.time() - 6 * 3600
    _put(db, SETPOINT, [(t0 - 3600, "102.0"), (t0, "104.0")])
    _put(db, WATER, [(t0 - 600, "102.0"), (t0 + 180, "103.0")])
    assert _run(db, pkg, "Hot Tub Heating Rate") is None


def test_heating_rate_ignores_implausible_start_readings(db, pkg):
    # 2026-10-28 19:44 live: a boot-time glitch read the water as 24F, giving a
    # "rate" of 23.9 F/min that dragged the weighted mean from ~0.1 to 0.52.
    t0 = time.time() - 6 * 3600
    _put(db, SETPOINT, [(t0 - 3600, "80.0"), (t0, "104.0")])
    _put(db, WATER, [(t0 - 60, "24.0"), (t0 + 200, "104.0")])
    assert _run(db, pkg, "Hot Tub Heating Rate") is None


# --- 3. the real recorder history (2026-10-27 .. 2026-11-07) ------------------

FIXTURE = Path(__file__).parent / "fixtures" / "thermal_history_2026-11-07.json"


@pytest.fixture
def real_db(db):
    import json

    data = json.loads(FIXTURE.read_text())
    shift = time.time() - data["end_ts"]  # keep it inside the 30-day window
    for entity_id, points in data["series"].items():
        _put(db, entity_id, [(ts + shift, state) for ts, state in points])
    return db


def test_real_history_heating_rate_matches_measured_heat_ups(real_db, pkg):
    # Measured heat-ups in this window take ~8-12 min per degree
    # (e.g. 11-07 05:00: 97 -> 103 in 62 min; 11-05 04:30: 100 -> 103 in 33 min).
    rate = _run(real_db, pkg, "Hot Tub Heating Rate")
    assert rate is not None
    assert 0.08 <= rate <= 0.12, f"{rate} F/min = {1 / rate:.1f} min/F"


def test_real_history_cooling_rate_matches_measured_overnight_loss(real_db, pkg):
    # Overnight coasts in this window lost 0.37-0.74 F/hr (2026-11-06 analysis).
    rate = _run(real_db, pkg, "Hot Tub Cooling Rate")
    assert rate is not None
    assert 0.3 <= rate <= 0.8
