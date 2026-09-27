"""Tests for sensor.hot_tub_water_temperature (ha/templates.yaml).

This sensor exists because sensor.tublemetry_hot_tub_temperature is unusable:
esphome/tublemetry.yaml filters it with `delta: 1.0`, ESPHome's delta test is
STRICTLY greater, and the panel decodes through atoi() -- so every real
one-degree step is exactly 1.0 and gets discarded, while setpoint flashes
(>= 2 F jumps) sail through. Observed twice on 2026-09-09, both times off by
exactly one from the panel.

The load-bearing test here is the 30-second stability gate. display_state reads
"temperature" for setpoint flashes as well as real readings -- it is set from
`is_numeric` before the in_set_mode_ check -- so duration is the ONLY signal
that separates them. Lose that gate and this sensor silently republishes the
same setpoint flashes it was built to filter out.
"""

from pathlib import Path

import jinja2
import pytest
import yaml

TEMPLATES_FILE = Path(__file__).parent.parent / "ha" / "templates.yaml"

DISPLAY = "sensor.tublemetry_hot_tub_display"


@pytest.fixture
def block():
    """The trigger-based template block defining the water temperature sensor."""
    data = yaml.safe_load(TEMPLATES_FILE.read_text())
    for b in data["template"]:
        for s in b.get("sensor", []) or []:
            if s.get("name") == "Hot Tub Water Temperature":
                return b
    raise AssertionError("Hot Tub Water Temperature is not defined")


@pytest.fixture
def sensor(block):
    return next(s for s in block["sensor"] if s["name"] == "Hot Tub Water Temperature")


def _conditions(block):
    return block.get("condition", []) or []


def _templates(block):
    return [c["value_template"] for c in _conditions(block) if "value_template" in c]


def test_sensor_is_trigger_based(block):
    """A state-based template cannot HOLD its last value through a flash."""
    assert "trigger" in block, "must be trigger-based to skip rather than publish"


def test_reads_the_display_not_the_broken_sensor(sensor):
    state = sensor["state"]
    assert DISPLAY in state
    assert "tublemetry_hot_tub_temperature" not in state, (
        "must not source from the delta-filtered sensor this replaces"
    )


def test_has_a_stability_gate(block):
    """The one gate that separates a real reading from a setpoint flash."""
    joined = " ".join(_templates(block))
    assert "last_changed" in joined, "no stability gate -- flashes will get through"
    assert "30" in joined, "stability window is not the documented 30s"


def test_filters_on_display_state_temperature(block):
    assert any(
        c.get("entity_id") == "sensor.tublemetry_hot_tub_display_state"
        and c.get("state") == "temperature"
        for c in _conditions(block)
    )


def test_excludes_ha_driven_injections(block):
    assert any(
        c.get("entity_id") == "sensor.tublemetry_hot_tub_injection_phase"
        and c.get("state") == "idle"
        for c in _conditions(block)
    )


def test_has_a_heartbeat_trigger(block):
    """Trigger templates return `unknown` after a restart, and a steady display
    may never fire a state trigger. Without a heartbeat the sensor can stay
    unknown indefinitely."""
    platforms = [t.get("platform") for t in block["trigger"]]
    assert "time_pattern" in platforms, "no heartbeat -- can stay unknown after restart"


def test_state_trigger_waits_for_the_display_to_settle(block):
    state_triggers = [t for t in block["trigger"] if t.get("platform") == "state"]
    assert state_triggers, "no state trigger"
    assert any("for" in t for t in state_triggers), "fires before the display settles"


@pytest.mark.parametrize(
    "display,expected",
    [
        ("104", True),    # plausible water temp
        ("102", True),
        ("40", True),     # boundary
        ("115", True),    # boundary
        ("02", False),    # partial decode mid-transition
        ("2", False),
        ("   ", False),   # blank frame
        ("unavailable", False),
        ("999", False),
        ("39", False),
        ("116", False),
    ],
)
def test_range_guard_rejects_partial_decodes(block, display, expected):
    """Rendered against the real Jinja engine, not asserted from the YAML text."""
    guard = next(t for t in _templates(block) if "<=" in t and "last_changed" not in t)
    env = jinja2.Environment()
    env.globals["states"] = lambda eid: display
    assert env.from_string(guard).render().strip() == str(expected)


def test_declares_temperature_units(sensor):
    assert sensor["unit_of_measurement"] == "°F"
    assert sensor["device_class"] == "temperature"
    assert sensor["state_class"] == "measurement"
    assert "unique_id" in sensor, "no unique_id -- not renameable in the UI"
