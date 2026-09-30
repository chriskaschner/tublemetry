"""Structural tests for ha/basement_leak.yaml.

Two SONOFF SNZB-05P leak sensors on the basement floor. The alert choices were
made by the user on 2026-09-29 and are pinned here:

  - ordinary pushes, NOT iOS critical alerts (water there is inconvenient, not
    an emergency, so a false alarm must not break through silent / Focus);
  - a wet reading is trusted even when it arrives straight from 'unavailable'
    (the opposite of the fridge door's `from: "off"` gate -- a missed leak
    costs more than a spurious push).
"""

from pathlib import Path

import pytest
import yaml

LEAK_FILE = Path(__file__).parent.parent / "ha" / "basement_leak.yaml"

LEAK_SENSORS = {"binary_sensor.gym_leak", "binary_sensor.floor_drain_leak"}
BATTERIES = {"sensor.gym_leak_battery", "sensor.floor_drain_leak_battery"}


@pytest.fixture
def pkg():
    return yaml.safe_load(LEAK_FILE.read_text())


def _auto(pkg, auto_id):
    return next(a for a in pkg["automation"] if a["id"] == auto_id)


@pytest.fixture
def leak(pkg):
    return _auto(pkg, "basement_leak_detected")


@pytest.fixture
def loop(leak):
    return next(s for s in leak["action"] if "repeat" in s)["repeat"]


def _walk(node):
    """Yield every dict nested anywhere under node."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _pushes(node):
    return [d for d in _walk(node) if str(d.get("action", "")).startswith("notify.")]


# --- structure ---


def test_is_valid_package(pkg):
    assert isinstance(pkg, dict)
    assert isinstance(pkg.get("automation"), list)


# --- leak trigger ---


def test_triggers_on_both_sensors(leak):
    watched = set()
    for trig in leak["trigger"]:
        ids = trig["entity_id"]
        watched |= {ids} if isinstance(ids, str) else set(ids)
    assert watched == LEAK_SENSORS


def test_wet_reading_after_reconnect_is_trusted(leak):
    """User decision 2026-09-29: 'unavailable' -> 'on' must page. So the
    trigger may not carry a `from:` gate like fridge_door.yaml's."""
    for trig in leak["trigger"]:
        assert trig["platform"] == "state"
        assert trig["to"] == "on"
        assert "from" not in trig
        assert "for" not in trig, "a leak should page immediately, not after a delay"


def test_two_sensors_wet_at_once_both_alert(leak):
    """restart / single would drop the second sensor's alert. parallel keeps
    one run per wet sensor."""
    assert leak["mode"] == "parallel"


# --- leak alerting ---


def test_no_critical_alerts(pkg):
    """User decision 2026-09-29: ordinary pushes only. A critical alert would
    punch through silent mode for a non-emergency."""
    for push in _pushes(pkg):
        data = push.get("data", {}).get("data", {}) or {}
        assert "push" not in data, "no sound/critical payload overrides"
        assert "interruption-level" not in str(data)


def test_push_names_which_sensor(loop):
    push = _pushes(loop)[0]
    assert "location" in push["data"]["message"]


def test_reminders_replace_rather_than_stack(loop):
    """Tag is per sensor, so the gym and drain alerts do not overwrite each
    other but repeat nags of the same sensor do."""
    push = _pushes(loop)[0]
    assert "sensor" in push["data"]["data"]["tag"]


def test_reminders_are_capped(loop):
    """An uncapped loop pushes forever on a probe that stays bridged (mineral
    crust, a puddle that never dries)."""
    caps = [c for c in loop["while"] if "repeat.index" in str(c.get("value_template", ""))]
    assert caps, "repeat loop must be capped on repeat.index"


def test_loop_exits_as_soon_as_it_dries(loop):
    """Sleep between nags waits on the SAME sensor reading dry, so the dry
    confirmation is not held back by a stale delay. wait_template rather than a
    templated wait_for_trigger entity_id, which state triggers do not render."""
    wait = next(s for s in loop["sequence"] if "wait_template" in s)
    assert "is_state(sensor, 'off')" in wait["wait_template"]
    assert wait["continue_on_timeout"] is True
    assert "delay" not in str(loop["sequence"])


def test_loop_runs_only_while_wet(loop):
    conds = [str(c.get("value_template", "")) for c in loop["while"]]
    assert any("is_state(sensor, 'on')" in c for c in conds)


def test_sensor_variable_is_the_triggering_entity(leak):
    assert leak["variables"]["sensor"] == "{{ trigger.entity_id }}"


def test_dry_confirmation_and_notice_cleanup(leak):
    branch = next(s for s in leak["action"] if "if" in s)
    assert "is_state(sensor, 'off')" in branch["if"][0]["value_template"]
    then = branch["then"]
    assert any(s.get("action") == "persistent_notification.dismiss" for s in then)
    assert _pushes(then), "dry must be confirmed on the phone"
    # Anything else (still wet after the cap, or went unavailable mid-leak)
    # must leave a visible notice rather than falling silent.
    assert any(s.get("action") == "persistent_notification.create" for s in branch["else"])


# --- dead sensor / battery ---


def test_offline_watchdog_covers_both_and_needs_the_gateway_up(pkg):
    """A single sensor unavailable is a device problem; ALL Zigbee down is
    zigbee_health.yaml's job and must not double-page from here."""
    auto = _auto(pkg, "basement_leak_sensor_offline")
    trig = auto["trigger"][0]
    assert set(trig["entity_id"]) == LEAK_SENSORS
    assert trig["to"] == "unavailable"
    assert "for" in trig
    gate = [c for c in auto["condition"] if c.get("entity_id") == "binary_sensor.zigbee_gateway_up"]
    assert gate and gate[0]["state"] == "on"
    assert _pushes(auto)


def test_offline_notice_clears_on_recovery(pkg):
    auto = _auto(pkg, "basement_leak_sensor_back")
    trig = auto["trigger"][0]
    assert set(trig["entity_id"]) == LEAK_SENSORS
    assert trig["from"] == "unavailable"
    assert any(s.get("action") == "persistent_notification.dismiss" for s in _walk(auto["action"]))


def test_low_battery_alert(pkg):
    auto = _auto(pkg, "basement_leak_battery_low")
    trig = auto["trigger"][0]
    assert trig["platform"] == "numeric_state"
    assert set(trig["entity_id"]) == BATTERIES
    assert trig["below"] == 20
    assert _pushes(auto)


# --- which sensor fired first (user requirement 2026-09-29) ---
#
# The user does not know where the water comes from -- the exterior wall (gym
# sensor) or the floor drain. The ORDER the two go wet, and the gap between
# them, is the diagnostic. Recorder history purges (10 days by default) and
# does not compute order, so it is recorded explicitly in restart-safe helpers.


@pytest.fixture
def record(pkg):
    return _auto(pkg, "basement_leak_record_order")


def test_order_helpers_exist(pkg):
    texts = pkg["input_text"]
    for key in ("basement_leak_first", "basement_leak_second", "basement_leak_summary"):
        assert key in texts
        assert "initial" not in texts[key], "initial: would wipe the record on every restart"
    start = pkg["input_datetime"]["basement_leak_episode_start"]
    assert start["has_date"] and start["has_time"]


def test_order_is_recorded_serially(record):
    """Both sensors wet within the same second must not both think they were
    first. queued processes wet edges one at a time, in order."""
    assert record["mode"] == "queued"


def test_order_uses_the_same_trusted_trigger(record, leak):
    assert record["trigger"] == leak["trigger"]


def test_order_timestamp_is_the_state_change_not_run_time(record):
    """A queued run can start late; the event time is when the sensor changed."""
    assert "trigger.to_state.last_changed" in record["variables"]["event_ts"]


def test_episode_window_is_24h(record):
    assert "86400" in record["variables"]["in_episode"]


def test_late_reports_are_flagged(record):
    """A wet reading straight from 'unavailable' carries the reconnect time,
    not the time the water arrived. The record must say so, or the ordering it
    shows could be wrong."""
    assert "unavailable" in record["variables"]["late"]


def test_first_and_second_paths_record_and_push(record):
    choose = next(s for s in record["action"] if "choose" in s)
    first, second = choose["choose"]
    for branch in (first, second):
        seq = branch["sequence"]
        targets = {str(s.get("target", {}).get("entity_id")) for s in seq}
        assert "input_text.basement_leak_summary" in targets
        assert any(s.get("action") == "logbook.log" for s in seq)
        assert _pushes(seq)
    first_targets = {str(s.get("target", {}).get("entity_id")) for s in first["sequence"]}
    assert "input_datetime.basement_leak_episode_start" in first_targets
    assert "input_text.basement_leak_first" in first_targets
    # A fresh episode must clear the previous second sensor.
    clear = next(
        s for s in first["sequence"]
        if s.get("target", {}).get("entity_id") == "input_text.basement_leak_second"
    )
    assert clear["data"]["value"] == ""
    second_push = _pushes(second["sequence"])[0]
    assert "lead_text" in second_push["data"]["message"]
    # Re-wetting a sensor already recorded this episode still pushes.
    assert _pushes(choose["default"])


def test_leak_loop_leaves_the_first_push_to_the_recorder(loop):
    """The initial push carries the order, so it comes from the queued recorder.
    The alert loop waits first and only sends reminders."""
    assert "wait_template" in loop["sequence"][0]
