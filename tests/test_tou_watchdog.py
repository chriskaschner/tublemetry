"""Structural tests for ha/tou_watchdog.yaml.

The watchdog alerts when the confirmed setpoint stays out of step with the
expected TOU setpoint for >15 min, or when the schedule automation is disabled.
"""

from pathlib import Path

import pytest
import yaml

WATCHDOG_FILE = Path(__file__).parent.parent / "ha" / "tou_watchdog.yaml"


def _unwrap(path):
    data = yaml.safe_load(path.read_text())
    if isinstance(data, dict) and "automation" in data:
        return data["automation"][0]
    return data


@pytest.fixture
def wd():
    return _unwrap(WATCHDOG_FILE)


def test_is_automation_package():
    data = yaml.safe_load(WATCHDOG_FILE.read_text())
    assert isinstance(data, dict) and isinstance(data.get("automation"), list)


def test_alias_and_mode(wd):
    assert wd.get("alias") == "Hot Tub TOU Watchdog"
    assert wd.get("mode") == "single"


def test_trigger_ids(wd):
    ids = {t.get("id") for t in wd["trigger"]}
    assert ids == {"setpoint_stuck", "schedule_off"}


def test_setpoint_stuck_trigger(wd):
    trig = next(t for t in wd["trigger"] if t.get("id") == "setpoint_stuck")
    assert trig["platform"] == "template"
    assert trig.get("for", {}).get("minutes") == 15, "must sustain 15 min to avoid transients"
    tpl = trig["value_template"]
    assert "sensor.hot_tub_expected_setpoint" in tpl
    assert "number.tublemetry_hot_tub_setpoint" in tpl
    assert "binary_sensor.tublemetry_hot_tub_api_status" in tpl
    assert "input_boolean.thermal_runaway_active" in tpl


def test_schedule_off_trigger(wd):
    trig = next(t for t in wd["trigger"] if t.get("id") == "schedule_off")
    assert trig["platform"] == "state"
    assert trig["entity_id"] == "automation.hot_tub_tou_schedule"
    assert trig["to"] == "off"


def test_both_branches_notify(wd):
    choose = next(item["choose"] for item in wd["action"] if "choose" in item)
    notif_ids = set()
    for branch in choose:
        for act in branch["sequence"]:
            if act.get("action") == "persistent_notification.create":
                notif_ids.add(act["data"]["notification_id"])
    assert notif_ids == {"tou_watchdog_stuck", "tou_watchdog_disabled"}


def test_both_branches_push_to_phone(wd):
    choose = next(item["choose"] for item in wd["action"] if "choose" in item)
    for branch in choose:
        actions = [a.get("action") for a in branch["sequence"]]
        assert any(a and a.startswith("notify.") for a in actions), (
            "each branch should also push a phone notification"
        )
