"""Tests for ha/hot_tub_mode_light.yaml.

sensor.hot_tub_mode drives the ThirdReality nightlight (light.nightlight) as a
heat/cold indicator for the hot tub's current TOU tier. The two things that
must not regress:

- The tier comes from the COMMANDED setpoint against the midpoint of the two
  seasonal sliders, not from the heater relay (which cycles in both tiers and
  would just make the light flicker) and not from the schedule's "expected"
  value alone (which would go stale during a manual override).
- Any missing/offline input collapses to "offline", and the light goes OFF
  rather than holding a stale color.
"""

from pathlib import Path

import jinja2
import pytest
import yaml

PKG_FILE = Path(__file__).parent.parent / "ha" / "hot_tub_mode_light.yaml"

LIGHT = "light.nightlight"
MODE_SENSOR = "sensor.hot_tub_mode"
BRIGHTNESS_SENSOR = "sensor.hot_tub_nightlight_brightness"


@pytest.fixture
def pkg():
    return yaml.safe_load(PKG_FILE.read_text())


def _sensor(pkg, name):
    return next(
        s for block in pkg["template"] for s in block.get("sensor", []) or []
        if s.get("name") == name
    )


@pytest.fixture
def mode_sensor(pkg):
    return _sensor(pkg, "Hot Tub Mode")


@pytest.fixture
def brightness_sensor(pkg):
    return _sensor(pkg, "Hot Tub Nightlight Brightness")


@pytest.fixture
def auto(pkg):
    return next(a for a in pkg["automation"] if a["id"] == "hot_tub_mode_light")


def _render(template_str: str, **overrides: str) -> str:
    states = {
        "binary_sensor.tublemetry_hot_tub_api_status": "on",
        "number.tublemetry_hot_tub_setpoint": "102",
        "input_number.hot_tub_max_setpoint": "102",
        "input_number.hot_tub_coast_setpoint": "90",
        "sensor.nightlight_illuminance": "172",
        "input_number.hot_tub_nightlight_day_brightness": "10",
        "input_number.hot_tub_nightlight_night_brightness": "1",
        "input_number.hot_tub_nightlight_day_threshold": "20",
    }
    states.update(overrides)
    env = jinja2.Environment()
    env.globals["states"] = lambda eid: states.get(eid, "unknown")
    env.globals["is_state"] = lambda eid, val: states.get(eid, "unknown") == val
    return env.from_string(template_str).render().strip()


# --- structure ---


def test_is_valid_package(pkg):
    assert isinstance(pkg, dict)
    assert isinstance(pkg.get("template"), list)
    assert isinstance(pkg.get("automation"), list)


def test_mode_sensor_declared(mode_sensor):
    assert mode_sensor["unique_id"] == "hot_tub_mode"


# --- tier classification, rendered against the real Jinja engine ---


def test_at_max_reads_heat(mode_sensor):
    assert _render(mode_sensor["state"], **{"number.tublemetry_hot_tub_setpoint": "102"}) == "heat"


def test_at_coast_reads_cold(mode_sensor):
    assert _render(mode_sensor["state"], **{"number.tublemetry_hot_tub_setpoint": "90"}) == "cold"


def test_evening_preheat_tier_still_reads_heat(mode_sensor):
    """max - 2 (templates.yaml's preheat tier) is much closer to Max than to
    Coast and must classify as heat, not cold."""
    assert _render(mode_sensor["state"], **{"number.tublemetry_hot_tub_setpoint": "100"}) == "heat"


def test_exact_midpoint_reads_heat(mode_sensor):
    """(102 + 90) / 2 == 96 -- the >= boundary must resolve one way, not error."""
    assert _render(mode_sensor["state"], **{"number.tublemetry_hot_tub_setpoint": "96"}) == "heat"


def test_reflects_commanded_not_scheduled_value(mode_sensor):
    """A manual override can put the commanded setpoint on the opposite tier
    from the schedule; the light must follow what was actually sent."""
    assert _render(
        mode_sensor["state"],
        **{
            "number.tublemetry_hot_tub_setpoint": "90",
            "input_number.hot_tub_max_setpoint": "102",
        },
    ) == "cold"


@pytest.mark.parametrize(
    "overrides",
    [
        {"binary_sensor.tublemetry_hot_tub_api_status": "off"},
        {"number.tublemetry_hot_tub_setpoint": "unavailable"},
        {"number.tublemetry_hot_tub_setpoint": "unknown"},
        {"input_number.hot_tub_max_setpoint": "unavailable"},
        {"input_number.hot_tub_coast_setpoint": "unavailable"},
    ],
)
def test_missing_inputs_report_offline_not_a_stale_mode(mode_sensor, overrides):
    assert _render(mode_sensor["state"], **overrides) == "offline"


# --- day/night brightness sliders ---


def test_brightness_sliders_declared(pkg):
    inums = pkg["input_number"]
    for name in (
        "hot_tub_nightlight_day_brightness",
        "hot_tub_nightlight_night_brightness",
        "hot_tub_nightlight_day_threshold",
    ):
        assert name in inums, f"missing input_number.{name}"
        assert "initial" not in inums[name], (
            f"{name} must not set initial: -- every future deploy restarts HA "
            "and would wipe a tuned value back to it"
        )


def test_brightness_sliders_are_percent_bounded(pkg):
    for name in ("hot_tub_nightlight_day_brightness", "hot_tub_nightlight_night_brightness"):
        entry = pkg["input_number"][name]
        assert entry["min"] == 1 and entry["max"] == 100
        assert entry["unit_of_measurement"] == "%"


def test_bright_ambient_light_uses_day_brightness(brightness_sensor):
    assert _render(
        brightness_sensor["state"],
        **{
            "sensor.nightlight_illuminance": "172",
            "input_number.hot_tub_nightlight_day_brightness": "10",
            "input_number.hot_tub_nightlight_night_brightness": "1",
            "input_number.hot_tub_nightlight_day_threshold": "20",
        },
    ) == "10.0"


def test_dark_ambient_light_uses_night_brightness(brightness_sensor):
    assert _render(
        brightness_sensor["state"],
        **{
            "sensor.nightlight_illuminance": "5",
            "input_number.hot_tub_nightlight_day_brightness": "10",
            "input_number.hot_tub_nightlight_night_brightness": "1",
            "input_number.hot_tub_nightlight_day_threshold": "20",
        },
    ) == "1.0"


def test_missing_illuminance_falls_back_to_night_not_day(brightness_sensor):
    """A stuck/unavailable light sensor should fail toward the less obtrusive
    (dimmer) value, not the brighter one."""
    assert _render(
        brightness_sensor["state"],
        **{"sensor.nightlight_illuminance": "unavailable"},
    ) == "1.0"


# --- automation ---


def test_triggers_on_mode_change_brightness_change_light_recovery_and_ha_start(auto):
    platforms = {t.get("platform") for t in auto["trigger"]}
    assert platforms == {"state", "homeassistant"}

    state_triggers = [t for t in auto["trigger"] if t.get("platform") == "state"]
    assert any(t["entity_id"] == MODE_SENSOR for t in state_triggers)
    assert any(t["entity_id"] == BRIGHTNESS_SENSOR for t in state_triggers), (
        "must react to a day/night flip, not just a heat/cold change"
    )

    light_recovery = next(t for t in state_triggers if t["entity_id"] == LIGHT)
    assert light_recovery["from"] == "unavailable"

    assert any(t.get("event") == "start" for t in auto["trigger"])


def test_heat_branch_sets_a_warm_color_at_the_templated_brightness(auto):
    choose = next(s for s in auto["action"] if "choose" in s)["choose"]
    branch = next(c for c in choose if "'heat'" in c["conditions"])
    step = branch["sequence"][0]
    assert step["action"] == "light.turn_on"
    assert step["target"]["entity_id"] == LIGHT
    r, g, b = step["data"]["rgb_color"]
    assert r > b, "heat indicator should be warm (red-dominant), got rgb=(%d,%d,%d)" % (r, g, b)
    assert "brightness" in step["data"]["brightness_pct"], (
        "brightness must come from the day/night sensor, not a hardcoded number"
    )


def test_cold_branch_sets_a_cool_color_at_the_templated_brightness(auto):
    choose = next(s for s in auto["action"] if "choose" in s)["choose"]
    branch = next(c for c in choose if "'cold'" in c["conditions"])
    step = branch["sequence"][0]
    assert step["action"] == "light.turn_on"
    assert step["target"]["entity_id"] == LIGHT
    r, g, b = step["data"]["rgb_color"]
    assert b > r, "cold indicator should be cool (blue-dominant), got rgb=(%d,%d,%d)" % (r, g, b)
    assert "brightness" in step["data"]["brightness_pct"], (
        "brightness must come from the day/night sensor, not a hardcoded number"
    )


def test_default_branch_turns_the_light_off(auto):
    """Anything other than heat/cold (i.e. "offline") must not leave a stale
    color showing."""
    choose_step = next(s for s in auto["action"] if "choose" in s)
    default = choose_step["default"]
    assert len(default) == 1
    assert default[0]["action"] == "light.turn_off"
    assert default[0]["target"]["entity_id"] == LIGHT
