"""Tests for ha/vacuum.yaml -- script.vacuum_park, the "park the vacuum" Siri target.

The script is run from an iOS Shortcut ("Run Script"), so the phone gives no
feedback of its own. Every path must end in a push, and "heading home" must be
reported only after the vacuum actually changed state.

The decision template is rendered with jinja2 (the engine HA uses) for every
vacuum activity state, so the branch logic is tested, not just its shape.
"""

from pathlib import Path

import jinja2
import pytest

from ha_yaml import load_ha_yaml

HA_DIR = Path(__file__).parent.parent / "ha"
VACUUM_FILE = HA_DIR / "vacuum.yaml"
VACUUM = "vacuum.q5_pro"

_ENV = jinja2.Environment()


@pytest.fixture
def pkg():
    return load_ha_yaml(VACUUM_FILE)


@pytest.fixture
def script(pkg):
    return pkg["script"]["vacuum_park"]


def _plan_template(script) -> str:
    for step in script["sequence"]:
        if "variables" in step and "plan" in step["variables"]:
            return step["variables"]["plan"]
    raise AssertionError("vacuum_park has no `plan` variable")


def plan_for(script, state: str) -> str:
    tmpl = _ENV.from_string(_plan_template(script))
    return tmpl.render(states=lambda e: state if e == VACUUM else "unknown")


def _choose(script) -> dict:
    return next(s for s in script["sequence"] if "choose" in s)


def _branch(script, plan: str) -> list:
    for option in _choose(script)["choose"]:
        if f"'{plan}'" in str(option["conditions"]):
            return option["sequence"]
    raise AssertionError(f"no branch for plan {plan!r}")


def _actions(steps: list) -> list[str]:
    return [s["action"] for s in steps if "action" in s]


def test_is_script_package(pkg):
    assert set(pkg) == {"script"}


def test_alias_is_what_shortcuts_lists(script):
    # iOS Shortcuts "Run Script" shows the alias; the Siri shortcut is built from it.
    assert script["alias"] == "Vacuum: Park"


@pytest.mark.parametrize("state", ["cleaning", "paused", "idle", "error"])
def test_off_dock_states_send_it_home(script, state):
    assert plan_for(script, state) == "send_home"


def test_returning_is_left_alone(script):
    assert plan_for(script, "returning") == "already_returning"


def test_docked_is_left_alone(script):
    assert plan_for(script, "docked") == "already_docked"


@pytest.mark.parametrize("state", ["unavailable", "unknown"])
def test_unreachable_vacuum_is_reported(script, state):
    assert plan_for(script, state) == "offline"


def test_send_home_calls_return_to_base_on_the_q5(script):
    steps = _branch(script, "send_home")
    call = next(s for s in steps if s.get("action") == "vacuum.return_to_base")
    assert call["target"]["entity_id"] == VACUUM


@pytest.mark.parametrize("plan", ["already_returning", "already_docked"])
def test_no_command_when_already_home_or_heading_there(script, plan):
    assert not [a for a in _actions(_branch(script, plan)) if a.startswith("vacuum.")]


def test_offline_sends_no_command(script):
    default = _choose(script)["default"]
    assert not [a for a in _actions(default) if a.startswith("vacuum.")]


@pytest.mark.parametrize("plan", ["send_home", "already_returning", "already_docked"])
def test_every_branch_notifies(script, plan):
    assert "notify.mobile_app_chris_iphone" in _actions(_branch(script, plan))


def test_offline_notifies(script):
    assert "notify.mobile_app_chris_iphone" in _actions(_choose(script)["default"])


def test_send_home_confirms_before_claiming_success(script):
    steps = _branch(script, "send_home")
    names = [next(iter(s)) for s in steps]
    wait_i = names.index("wait_template")
    notify_i = next(i for i, s in enumerate(steps) if s.get("action", "").startswith("notify."))
    assert wait_i < notify_i
    wait = steps[wait_i]
    assert "returning" in wait["wait_template"] and "docked" in wait["wait_template"]
    assert wait["continue_on_timeout"] is True, "a timeout must still notify"
    assert "wait.completed" in str(steps[notify_i]["data"])


# --- script.vacuum_full_clean -----------------------------------------------
#
# Presses the "Full Cleaning" routine the user built in the Roborock app, so the
# rooms and suction settings live there, not here. Same contract as park: every
# path pushes, and "started" is only claimed once the vacuum reports cleaning.

FULL_CLEAN_BUTTON = "button.q5_pro_full_cleaning"


@pytest.fixture
def full_clean(pkg):
    return pkg["script"]["vacuum_full_clean"]


def test_full_clean_alias_is_what_shortcuts_lists(full_clean):
    assert full_clean["alias"] == "Vacuum: Full Clean"


@pytest.mark.parametrize("state", ["docked", "idle", "paused", "returning"])
def test_full_clean_starts_from_any_resting_state(full_clean, state):
    assert plan_for(full_clean, state) == "start"


def test_full_clean_leaves_a_running_clean_alone(full_clean):
    assert plan_for(full_clean, "cleaning") == "already_cleaning"


def test_full_clean_does_not_start_while_in_error(full_clean):
    # An error (stuck, brush jammed, bin out) needs a human; pressing the routine
    # would just fail again or be ignored.
    assert plan_for(full_clean, "error") == "error"


@pytest.mark.parametrize("state", ["unavailable", "unknown"])
def test_full_clean_reports_unreachable(full_clean, state):
    assert plan_for(full_clean, state) == "offline"


def test_full_clean_presses_the_roborock_routine(full_clean):
    steps = _branch(full_clean, "start")
    press = next(s for s in steps if s.get("action") == "button.press")
    assert press["target"]["entity_id"] == FULL_CLEAN_BUTTON


@pytest.mark.parametrize("plan", ["already_cleaning", "error"])
def test_full_clean_sends_nothing_when_it_should_not_start(full_clean, plan):
    acts = _actions(_branch(full_clean, plan))
    assert not [a for a in acts if a.startswith(("vacuum.", "button."))]
    assert "notify.mobile_app_chris_iphone" in acts


def test_full_clean_offline_notifies_without_a_command(full_clean):
    acts = _actions(_choose(full_clean)["default"])
    assert not [a for a in acts if a.startswith(("vacuum.", "button."))]
    assert "notify.mobile_app_chris_iphone" in acts


def test_full_clean_confirms_before_claiming_it_started(full_clean):
    steps = _branch(full_clean, "start")
    names = [next(iter(s)) for s in steps]
    wait = steps[names.index("wait_template")]
    notify_i = next(i for i, s in enumerate(steps) if s.get("action", "").startswith("notify."))
    assert names.index("wait_template") < notify_i
    assert "cleaning" in wait["wait_template"]
    assert wait["continue_on_timeout"] is True
    assert "wait.completed" in str(steps[notify_i]["data"])
