"""Structural tests for ha/fridge_door.yaml.

Escalating alerts are easy to get wrong in two opposite directions: nagging
forever on a stuck sensor, or exiting the loop so late that the "closed"
confirmation arrives minutes after the fact. Both are pinned here.
"""

from pathlib import Path

import pytest
import yaml

FRIDGE_FILE = Path(__file__).parent.parent / "ha" / "fridge_door.yaml"

DOOR_SENSOR = "binary_sensor.openclose_5"


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


def test_triggers_on_door_open_for_threshold(auto):
    trig = auto["trigger"][0]
    assert DOOR_SENSOR in trig["value_template"]
    assert "fridge_door_open_minutes" in str(trig["for"]["minutes"])


def test_uses_template_trigger_for_templated_for(auto):
    """HA documents template support in `for:` for TEMPLATE triggers only. A
    state trigger with a templated `for:` is undocumented and may silently
    ignore the slider, so the threshold would quietly stop being tunable."""
    assert auto["trigger"][0]["platform"] == "template"


def test_ignores_unavailable_sensor(auto):
    """'unavailable' is not 'open' -- a sensor that dropped off the mesh must
    not be reported as a door left ajar."""
    conds = auto["condition"]
    assert any(
        c.get("entity_id") == DOOR_SENSOR and c.get("state") == "on" for c in conds
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
