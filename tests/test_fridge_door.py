"""Structural tests for ha/fridge_door.yaml.

Escalating alerts are easy to get wrong in two opposite directions: nagging
forever on a stuck sensor, or exiting the loop so late that the "closed"
confirmation arrives minutes after the fact. Both are pinned here.
"""

from pathlib import Path

import pytest
import yaml

FRIDGE_FILE = Path(__file__).parent.parent / "ha" / "fridge_door.yaml"

DOOR_SENSOR = "binary_sensor.fridge_door"


@pytest.fixture
def pkg():
    return yaml.safe_load(FRIDGE_FILE.read_text())


@pytest.fixture
def auto(pkg):
    return next(a for a in pkg["automation"] if a["id"] == "fridge_door_left_open")


@pytest.fixture
def loop(auto):
    return next(s for s in auto["action"] if "repeat" in s)["repeat"]


# --- structure ---


def test_is_valid_package(pkg):
    assert isinstance(pkg, dict)
    assert isinstance(pkg.get("automation"), list)
    assert "input_number" in pkg and "input_boolean" in pkg


def test_threshold_is_a_slider_with_safe_default(pkg):
    """No `initial:` means it comes up at min, so min must be the value we
    actually want (3 min) rather than something that nags instantly."""
    entry = pkg["input_number"]["fridge_door_open_minutes"]
    assert "initial" not in entry
    assert entry["min"] == 3


# --- trigger ---


def test_triggers_only_on_a_real_open_edge(auto):
    """REGRESSION (2026-09-09): the deCONZ gateway drops out ~9x/day and each
    reconnect repopulated this entity as 'on', which the old "state is 'on' for
    N minutes" trigger could not distinguish from a door left ajar -- roughly 9
    false pushes a day. Demanding an 'off' -> 'on' edge excludes
    'unavailable' -> 'on'. Do not relax `from` without re-reading the header."""
    trig = auto["trigger"][0]
    assert trig["platform"] == "state"
    assert trig["entity_id"] == DOOR_SENSOR
    assert trig["from"] == "off"
    assert trig["to"] == "on"


def test_threshold_is_still_tunable_by_the_slider(auto):
    """The threshold moved out of the trigger `for:` and into the first
    wait_for_trigger `timeout`. It must still read the slider, in seconds."""
    wait = auto["action"][0]
    assert "wait_for_trigger" in wait
    assert "fridge_door_open_minutes" in wait["timeout"]
    assert "* 60" in wait["timeout"], "timeout is in seconds, so minutes must be scaled"
    assert wait["continue_on_timeout"] is True


def test_closing_inside_the_threshold_sends_nothing(auto):
    """A normal grab from the fridge completes the wait, so wait.trigger is set.
    Only a timeout (wait.trigger is none) means the door is still open."""
    gate = next(
        s for s in auto["action"] if str(s.get("value_template", "")).count("wait.trigger")
    )
    assert "is none" in gate["value_template"]


def test_ignores_unavailable_sensor(auto):
    """'unavailable' is not 'open' -- a sensor that dropped off the mesh mid-wait
    must not be reported as a door left ajar."""
    assert any(
        s.get("entity_id") == DOOR_SENSOR and s.get("state") == "on"
        for s in auto["action"]
    )


def test_restart_mode_allows_a_fresh_cycle(auto):
    """close-then-reopen must start a new alert cycle, not be swallowed by the
    previous run still sitting in its wait."""
    assert auto["mode"] == "restart"


# --- escalation loop ---


def test_nagging_is_capped(loop):
    """An uncapped loop would push forever on a sensor stuck 'on', which is
    exactly what a dead magnet looks like."""
    caps = [
        c["value_template"]
        for c in loop["while"]
        if c.get("condition") == "template"
    ]
    assert caps, "loop has no iteration cap"
    assert "repeat.index" in caps[0]


def test_loop_exits_when_door_closes(loop):
    assert any(
        c.get("entity_id") == DOOR_SENSOR and c.get("state") == "on"
        for c in loop["while"]
    )


def test_loop_wakes_immediately_on_close(loop):
    """A plain 5-min delay would leave the loop asleep after the door shuts and
    delay the confirmation; waiting on the close event exits promptly."""
    wait = next(s for s in loop["sequence"] if "wait_for_trigger" in s)
    assert wait["wait_for_trigger"][0]["entity_id"] == DOOR_SENSOR
    assert wait["wait_for_trigger"][0]["to"] == "off"
    assert wait["timeout"] == "00:05:00"
    assert wait["continue_on_timeout"] is True


def test_reminders_replace_rather_than_stack(loop):
    """Twelve stacked banners for one open door is unusable on a phone."""
    notify = next(
        s for s in loop["sequence"] if s.get("action", "").startswith("notify.")
    )
    assert notify["data"]["data"]["tag"] == "fridge_door_open"


# --- resolution ---


def test_confirms_when_closed(auto):
    branch = next(s for s in auto["action"] if "if" in s)
    actions = [s.get("action") for s in branch["then"]]
    assert "notify.mobile_app_chris_iphone" in actions
    assert "persistent_notification.dismiss" in actions


def test_gives_up_loudly_not_silently(auto):
    """After the cap, stop pushing but leave something behind -- a still-open
    outdoor fridge should not simply be forgotten."""
    branch = next(s for s in auto["action"] if "if" in s)
    actions = [s.get("action") for s in branch["else"]]
    assert "persistent_notification.create" in actions
    assert "system_log.write" in actions


# --- stuck-sensor watchdog (covers the gap the 'off' -> 'on' gate opens) ---


@pytest.fixture
def stuck(pkg):
    return next(
        a for a in pkg["automation"] if a["id"] == "fridge_door_sensor_stuck_open"
    )


def test_watchdog_covers_the_untrusted_transition(stuck):
    """The gate deliberately drops 'unavailable' -> 'on'. That is exactly what
    this watches, so a door opened during a dropout is not invisible."""
    trig = stuck["trigger"][0]
    assert trig["from"] == "unavailable"
    assert trig["to"] == "on"
    assert trig["for"]["minutes"] == 60


def test_watchdog_never_pushes(stuck):
    """Pushing here would reinstate the false alerts on a 60-minute lag, which
    is the entire thing the gate exists to stop."""
    actions = [s.get("action", "") for s in stuck["action"]]
    assert not any(a.startswith("notify.") for a in actions)
    assert "persistent_notification.create" in actions
    assert "system_log.write" in actions


def test_watchdog_notice_is_cleared_on_a_real_close(pkg):
    """Otherwise a stale 'reads open' banner outlives the fault."""
    clear = next(
        a for a in pkg["automation"] if a["id"] == "fridge_door_stuck_cleared"
    )
    assert clear["trigger"][0]["to"] == "off"
    assert clear["action"][0]["action"] == "persistent_notification.dismiss"

    stuck_auto = next(
        a for a in pkg["automation"] if a["id"] == "fridge_door_sensor_stuck_open"
    )
    created = next(
        s for s in stuck_auto["action"]
        if s.get("action") == "persistent_notification.create"
    )
    assert clear["action"][0]["data"]["notification_id"] == created["data"]["notification_id"]


def _walk(node):
    """Yield every action step, including ones nested in if/then/else, repeat,
    and choose. The give-up notification lives inside an if/else branch."""
    if isinstance(node, list):
        for item in node:
            yield from _walk(item)
    elif isinstance(node, dict):
        yield node
        for key in ("then", "else", "sequence", "default"):
            if key in node:
                yield from _walk(node[key])
        if "repeat" in node:
            yield from _walk(node["repeat"].get("sequence", []))
        if "choose" in node:
            for option in node["choose"]:
                yield from _walk(option.get("sequence", []))


def test_watchdog_notice_is_distinct_from_the_alert_notice(pkg):
    """Sharing an id would let the give-up branch and the watchdog silently
    overwrite each other's notification."""
    ids = {
        s["data"]["notification_id"]
        for a in pkg["automation"]
        for s in _walk(a["action"])
        if s.get("action") == "persistent_notification.create"
    }
    assert ids == {"fridge_door_open", "fridge_door_stuck"}, f"got {ids}"
