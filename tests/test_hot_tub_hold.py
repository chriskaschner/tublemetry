"""Tests for the hot tub away hold (helpers.yaml, templates.yaml, hot_tub_hold.yaml).

Design (2026-09-27): the hold is part of the SCHEDULE, not the override. While
input_boolean.hot_tub_away_hold is on, sensor.hot_tub_expected_setpoint reports
input_number.hot_tub_hold_setpoint instead of the TOU value. Everything that
already follows the expected setpoint then does the right thing for free:
tou_automation re-applies it after every WiFi drop / HA restart / ESP32
reconnect, and tou_watchdog pages if the tub drifts off it while you are away.

The scripts exist for Siri and for feedback. Two traps they must avoid:

1. DOUBLE COMMAND. Toggling the hold usually changes the expected setpoint,
   which fires tou_automation. If the script ALSO commanded the setpoint, the
   second identical command would hit the known no-op bug (runs the full retry
   ladder against zero presses, latches last_command_result = failed).
2. NO COMMAND. If the hold temperature equals what the schedule already wants,
   the expected setpoint does not change, tou_automation never fires, and a tub
   left at 104 by an earlier "turn on" override stays at 104.

So the script commands the setpoint itself ONLY when the expected value did not
change and the commanded value disagrees with it.
"""

from pathlib import Path

import jinja2
import pytest

from ha_yaml import load_ha_yaml
from test_expected_setpoint import _expected_setpoint_template, at, WED

HA_DIR = Path(__file__).parent.parent / "ha"
HOLD_FILE = HA_DIR / "hot_tub_hold.yaml"
HELPERS_FILE = HA_DIR / "helpers.yaml"
TOU_FILE = HA_DIR / "tou_automation.yaml"

HOLD_FLAG = "input_boolean.hot_tub_away_hold"
HOLD_TEMP = "input_number.hot_tub_hold_setpoint"
OVERRIDE = "input_boolean.hot_tub_manual_override"
COMMANDED = "number.tublemetry_hot_tub_setpoint"

_ENV = jinja2.Environment()


def expected(when, maxsp=102, coast=90, hold="off", hold_temp=90):
    tmpl = _ENV.from_string(_expected_setpoint_template())
    vals = {
        "input_number.hot_tub_max_setpoint": str(maxsp),
        "input_number.hot_tub_coast_setpoint": str(coast),
        HOLD_FLAG: hold,
        HOLD_TEMP: str(hold_temp),
    }
    return int(tmpl.render(now=lambda: when, states=lambda e: vals.get(e, "unknown")).strip())


# --- The schedule honors the hold -------------------------------------------

class TestExpectedSetpointHold:
    def test_hold_overrides_a_max_window(self):
        assert expected(at(WED, 19, 30), hold="on", hold_temp=90) == 90

    def test_hold_overrides_a_coast_window(self):
        assert expected(at(WED, 23, 0), coast=90, hold="on", hold_temp=95) == 95

    def test_hold_off_leaves_the_schedule_alone(self):
        assert expected(at(WED, 19, 30), hold="off") == 102
        assert expected(at(WED, 12, 0), hold="off") == 90

    def test_hold_is_constant_all_week(self):
        # No TOU boundaries while away: the value never changes, so neither
        # tou_automation nor the override expiry fires for a week.
        vals = {expected(at(WED, h, m), hold="on", hold_temp=92)
                for h in range(24) for m in (0, 30)}
        assert vals == {92}

    @pytest.mark.parametrize("state", ["unknown", "unavailable"])
    def test_unknown_hold_flag_falls_back_to_the_schedule(self, state):
        # Right after a restart the boolean can read unknown for a moment. Never
        # treat that as "hold on".
        assert expected(at(WED, 19, 30), hold=state) == 102

    def test_unknown_hold_temp_does_not_produce_a_bogus_value(self):
        # A hold with no usable temperature falls back to the schedule rather
        # than an out-of-range number.
        tmpl = _ENV.from_string(_expected_setpoint_template())
        vals = {"input_number.hot_tub_max_setpoint": "102",
                "input_number.hot_tub_coast_setpoint": "90",
                HOLD_FLAG: "on", HOLD_TEMP: "unknown"}
        out = int(tmpl.render(now=lambda: at(WED, 19, 30), states=lambda e: vals.get(e, "unknown")).strip())
        assert out == 102


# --- Helpers ------------------------------------------------------------------

@pytest.fixture
def helpers():
    return load_ha_yaml(HELPERS_FILE)


def test_hold_flag_defined(helpers):
    assert "hot_tub_away_hold" in helpers["input_boolean"]


def test_hold_temp_slider_uses_the_firmware_clamp(helpers):
    slider = helpers["input_number"]["hot_tub_hold_setpoint"]
    assert slider["min"] == 80 and slider["max"] == 104 and slider["step"] == 1


def test_hold_temp_has_no_initial(helpers):
    # `initial` re-applies on EVERY restart and would wipe a chosen hold temp
    # (same reason as the seasonal sliders, see helpers.yaml).
    assert "initial" not in helpers["input_number"]["hot_tub_hold_setpoint"]
    assert "initial" not in helpers["input_boolean"]["hot_tub_away_hold"]


# --- tou_automation already covers the hold, unchanged ------------------------

def test_tou_automation_still_applies_on_expected_change():
    tou = load_ha_yaml(TOU_FILE)["automation"][0]
    ids = {t.get("id") for t in tou["trigger"]}
    assert {"expected_changed", "esp32_online", "ha_start"} <= ids


# --- Scripts ------------------------------------------------------------------
#
# Same shape as hot_tub_button.yaml: the logic lives in one script,
# hot_tub_hold_apply(hold), and the two Siri-facing scripts only delegate.

@pytest.fixture
def pkg():
    return load_ha_yaml(HOLD_FILE)


@pytest.fixture
def apply(pkg):
    return pkg["script"]["hot_tub_hold_apply"]


def _index(steps, pred):
    return next(i for i, s in enumerate(steps) if pred(s))


def _is_action(name, entity=None):
    def pred(s):
        if s.get("action") != name:
            return False
        return entity is None or s.get("target", {}).get("entity_id") == entity
    return pred


def _flip_index(steps):
    return _index(steps, lambda s: "if" in s and HOLD_FLAG in str(s.get("then", "")))


def test_is_script_package(pkg):
    assert set(pkg) == {"script"}


@pytest.mark.parametrize("name,alias,hold", [
    ("hot_tub_hold_on", "Hot Tub: Hold On", True),
    ("hot_tub_hold_off", "Hot Tub: Hold Off", False),
])
def test_wrappers_delegate_with_the_right_flag(pkg, name, alias, hold):
    script = pkg["script"][name]
    assert script["alias"] == alias
    assert script["sequence"] == [
        {"action": "script.hot_tub_hold_apply", "data": {"hold": hold}}
    ]


def test_flip_sets_the_flag_both_ways(apply):
    step = apply["sequence"][_flip_index(apply["sequence"])]
    assert _is_action("input_boolean.turn_on", HOLD_FLAG)(step["then"][0])
    assert _is_action("input_boolean.turn_off", HOLD_FLAG)(step["else"][0])


def test_override_cleared_before_the_hold_flips(apply):
    # With the override off, hot_tub_override_expiry's condition is false, so the
    # expected-setpoint change does not ALSO push a misleading "schedule boundary
    # reached" notification on top of the script's own.
    steps = apply["sequence"]
    clear = _index(steps, _is_action("input_boolean.turn_off", OVERRIDE))
    assert clear < _flip_index(steps)


def test_expected_is_captured_before_the_flip(apply):
    steps = apply["sequence"]
    before = _index(steps, lambda s: "variables" in s and "expected_before" in s["variables"])
    assert before < _flip_index(steps)
    assert "sensor.hot_tub_expected_setpoint" in steps[before]["variables"]["expected_before"]


def _command_step(steps):
    return steps[_index(steps, lambda s: "if" in s and any(
        t.get("action") == "number.set_value" for t in s.get("then", [])))]


def test_commands_only_when_the_schedule_will_not(apply):
    steps = apply["sequence"]
    cond = str(_command_step(steps)["if"])
    assert "expected_before" in cond, "must compare against the pre-flip expected value"
    assert COMMANDED in cond, "must skip when the tub is already commanded there"
    # Script variables are rendered to native types (90, not "90"), so the
    # comparison must coerce both sides or it is always "changed" -> "unchanged"
    # misfires into a double command.
    assert "expected_before | int" in cond
    assert not any(s.get("action") == "number.set_value" for s in steps)


def test_command_is_gated_on_safety(apply):
    cond = str(_command_step(apply["sequence"])["if"])
    assert "blocked" in cond


def test_blocked_covers_runaway_and_offline(apply):
    steps = apply["sequence"]
    var = next(s["variables"]["blocked"] for s in steps
               if "variables" in s and "blocked" in s["variables"])
    assert "thermal_runaway_active" in var
    assert "tublemetry_hot_tub_api_status" in var


def test_reports_reality_not_intent(apply):
    steps = apply["sequence"]
    wait_i = _index(steps, lambda s: "wait_template" in s)
    notify_i = _index(steps, lambda s: s.get("action") == "notify.mobile_app_chris_iphone")
    assert wait_i < notify_i
    wait = steps[wait_i]
    assert "sensor.tublemetry_hot_tub_detected_setpoint" in wait["wait_template"]
    assert "sensor.tublemetry_hot_tub_injection_phase" in wait["wait_template"]
    assert wait["continue_on_timeout"] is True
    data = str(steps[notify_i]["data"])
    assert "wait.completed" in data
    # A blocked or offline tub must be explained, not reported as a timeout.
    assert "blocked" in data
