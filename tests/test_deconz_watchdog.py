"""Structural tests for ha/deconz_watchdog.yaml.

This package restarts an add-on automatically, so the failure modes are worse
than a missed alert: a bad threshold either restarts a healthy gateway or never
fires, and a missing cooldown turns a freeze into a restart loop. Those are the
properties pinned here.

The CPU thresholds come from a measured freeze on 2026-09-09 (healthy median
1.38%, frozen median 0.35%, no overlap). Do not retune them from intuition --
re-measure with scripts/watch_deconz_health.py first.
"""

from pathlib import Path

import pytest
import yaml

WATCHDOG_FILE = Path(__file__).parent.parent / "ha" / "deconz_watchdog.yaml"

CPU_SENSOR = "sensor.deconz_cpu_percent"
ADDON_SLUG = "core_deconz"
COUNTER = "counter.deconz_watchdog_restarts"


@pytest.fixture
def pkg():
    return yaml.safe_load(WATCHDOG_FILE.read_text())


@pytest.fixture
def watchdog(pkg):
    return next(a for a in pkg["automation"] if a["id"] == "deconz_freeze_watchdog")


# --- gateway health sensor ---


def test_gateway_sensor_needs_two_witnesses(pkg):
    """One battery device dropping off the mesh is that device's problem. Both
    deCONZ devices going unavailable at once is the gateway -- that byte-identical
    correlation is exactly how the fault was diagnosed."""
    sensor = pkg["template"][0]["binary_sensor"][0]
    assert sensor["unique_id"] == "deconz_gateway_up"
    state = sensor["state"]
    assert "sensor.temperature_3" in state
    assert "binary_sensor.openclose_5" in state
    assert " and " in state, "witnesses must both be unavailable, not either"


def test_gateway_sensor_does_not_depend_on_the_cpu_sensor(pkg):
    """The CPU sensor is disabled by default in the entity registry and could be
    disabled again. Consumers gating alerts on gateway health must not silently
    break if that happens."""
    assert CPU_SENSOR not in pkg["template"][0]["binary_sensor"][0]["state"]


# --- trigger ---


def test_triggers_in_the_gap_between_measured_states(watchdog):
    """Frozen maxed at 0.39% and healthy bottomed at 1.31%, so 0.8 sits in the
    empty middle with margin both ways."""
    trig = watchdog["trigger"][0]
    assert trig["platform"] == "numeric_state"
    assert trig["entity_id"] == CPU_SENSOR
    assert 0.4 < trig["below"] < 1.3, "threshold is outside the measured gap"


def test_confirms_before_acting(watchdog):
    """The CPU drop leads HA's own detection by 5.8 min, so there is room to
    confirm and still beat the median 53-minute outage by a wide margin."""
    assert watchdog["trigger"][0]["for"]["minutes"] >= 5


def test_does_not_fight_a_deliberate_stop(watchdog):
    """If someone stopped the add-on on purpose, restarting it is wrong."""
    assert any(
        c.get("entity_id") == "binary_sensor.deconz_running" and c.get("state") == "on"
        for c in watchdog["condition"]
    )


# --- action ---


def _actions(steps):
    return [s.get("action") for s in steps]


def test_restarts_the_right_addon(watchdog):
    """A wrong slug fails silently -- the automation runs green and nothing
    restarts. Verified against the device registry: ['hassio', 'core_deconz']."""
    step = next(s for s in watchdog["action"] if s.get("action") == "hassio.addon_restart")
    assert step["data"]["addon"] == ADDON_SLUG


def test_verifies_the_restart_actually_worked(watchdog):
    """A restart that does not recover CPU means this mitigation is not the
    answer for whatever is happening, which is worth knowing immediately rather
    than discovering later from missing data."""
    wait = next(s for s in watchdog["action"] if "wait_template" in s)
    assert CPU_SENSOR in wait["wait_template"]
    assert wait["continue_on_timeout"] is True

    branch = next(s for s in watchdog["action"] if "if" in s)
    assert "wait.completed" in branch["if"][0]["value_template"]
    assert any(a and a.startswith("notify.") for a in _actions(branch["then"])), \
        "a failed restart must page -- it means Zigbee is still down"


def test_has_a_cooldown_so_it_cannot_loop(watchdog):
    """mode:single plus a trailing delay is what stops a freeze that resumes
    immediately from becoming a restart loop."""
    assert watchdog["mode"] == "single"
    assert any("delay" in s for s in watchdog["action"])


def test_routine_restarts_do_not_push(watchdog):
    """~8 restarts/day is the expected steady state until the root cause is
    found. Pushing each one is how the fridge alert became ignorable."""
    top_level = _actions(watchdog["action"])
    assert not any(a and a.startswith("notify.") for a in top_level), \
        "restart path pushes unconditionally"


def test_counts_restarts(watchdog):
    step = next(s for s in watchdog["action"] if s.get("action") == "counter.increment")
    assert step["target"]["entity_id"] == COUNTER


# --- rate guard ---


def test_excessive_restarts_are_escalated(pkg):
    """If restarting stops holding, the mitigation is failing and that is a
    different problem from the baseline freeze."""
    auto = next(a for a in pkg["automation"] if a["id"] == "deconz_watchdog_excessive")
    trig = auto["trigger"][0]
    assert trig["entity_id"] == COUNTER
    assert trig["above"] > 8, "must sit above the measured ~8 freezes/day baseline"
    assert "persistent_notification.create" in _actions(auto["action"])


def test_counter_resets_daily(pkg):
    """Otherwise the excessive-rate check trips once and stays tripped forever."""
    auto = next(a for a in pkg["automation"] if a["id"] == "deconz_watchdog_daily_reset")
    assert auto["trigger"][0]["platform"] == "time"
    actions = _actions(auto["action"])
    assert "counter.reset" in actions
    assert "persistent_notification.dismiss" in actions, \
        "resetting the counter must also clear the banner it raised"
