"""Tests for ha/hot_tub_heat_guard.yaml.

WHY THIS EXISTS (2026-11-06): the panel went into Economy mode (display "Ec")
at 17:21 on 11-05, nobody noticed, and the next morning the 04:30 raise to
104F was accepted and verified but the heater did not run until the 06:49
filter cycle. The tub was cold at use time and nothing alerted. Two guards:

1. Heat start guard: the confirmed setpoint rises above the water temperature
   and neither the pump nor the heater comes on within 10 min. Keyed on the
   pump as well as the heater because the pump bit is the one that survived the
   pre-0.3.1 decode bug (heater on + water <= 99F froze the heater bit).
2. Panel mode alert: the panel sits in Economy or Sleep for 2 min.
   sensor.hot_tub_panel_mode latches the mode, because in Economy the display
   alternates "Ec" with the temperature, so display_state itself never holds a
   value long enough for a `for:`.

NOTE ON "standby": the firmware labels the "St" / "5t" display "standby", but
on a Balboa panel St is STANDARD mode -- it is what the display shows when you
select Standard. So "standby" means healthy here, never an alert.

Templates are rendered with jinja2 (the engine HA uses) against stand-ins for
HA's states(), is_state(), now(), as_datetime(), `this` and `trigger`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import jinja2
import pytest

from ha_yaml import load_ha_yaml

PKG_FILE = Path(__file__).parent.parent / "ha" / "hot_tub_heat_guard.yaml"
NOW = datetime(2026, 11, 6, 4, 40, tzinfo=timezone(timedelta(hours=-6)))


@pytest.fixture(scope="module")
def pkg():
    return load_ha_yaml(PKG_FILE)


@pytest.fixture(scope="module")
def mode_sensor(pkg):
    for block in pkg["template"]:
        for s in block.get("sensor", []):
            if s.get("unique_id") == "hot_tub_panel_mode":
                return s, block
    raise AssertionError("sensor.hot_tub_panel_mode not defined")


@pytest.fixture(scope="module")
def guard(pkg):
    return next(a for a in pkg["automation"] if a["id"] == "hot_tub_heat_start_guard")


@pytest.fixture(scope="module")
def mode_alert(pkg):
    return next(a for a in pkg["automation"] if a["id"] == "hot_tub_panel_mode_alert")


def _state(state: str, last_reported: datetime | None = None, attributes: dict | None = None):
    return SimpleNamespace(state=state, last_reported=last_reported or NOW,
                           attributes=attributes or {})


def render(template: str, states: dict | None = None, objs: dict | None = None, **ctx) -> str:
    """Render an HA template. `states` maps entity_id -> state string; `objs`
    maps entity_id -> state object for templates that use states.domain.name."""
    states = states or {}
    objs = objs or {}
    env = jinja2.Environment()
    env.globals["states"] = _States(states, objs)
    env.globals["is_state"] = lambda eid, val: states.get(eid, "unknown") == val
    env.globals["now"] = lambda: NOW
    env.globals["as_datetime"] = lambda v: datetime.fromisoformat(v) if v else None
    return env.from_string(template).render(**ctx).strip()


class _States:
    """Callable like HA's states('x.y') and attribute-accessible like states.x.y."""

    def __init__(self, states: dict, objs: dict):
        self._states, self._objs = states, objs

    def __call__(self, eid: str) -> str:
        return self._states.get(eid, "unknown")

    def __getattr__(self, domain: str):
        objs = self._objs
        return SimpleNamespace(**{eid.split(".", 1)[1]: o for eid, o in objs.items()
                                  if eid.startswith(domain + ".")})


DS = "sensor.tublemetry_hot_tub_display_state"


def _this(state: str = "standard", seen: datetime | None = None):
    attrs = {"mode_seen": seen.isoformat()} if seen else {}
    return SimpleNamespace(state=state, attributes=attrs)


# --- structure ---------------------------------------------------------------


def test_is_valid_package(pkg):
    assert isinstance(pkg.get("template"), list)
    assert isinstance(pkg.get("automation"), list)


def test_registered_as_automation_file():
    from test_packages import AUTOMATION_FILES
    assert PKG_FILE.name in AUTOMATION_FILES


def test_mode_sensor_retriggers_on_display_change_and_every_minute(mode_sensor):
    _, block = mode_sensor
    trigs = block["trigger"]
    assert any(t.get("platform") == "state" and t.get("entity_id") == DS for t in trigs)
    assert any(t.get("platform") == "time_pattern" and t.get("minutes") == "/1" for t in trigs), (
        "needs a periodic re-render so the latch can decay and steady 'Ec' keeps refreshing"
    )


# --- panel mode latch, rendered ----------------------------------------------


@pytest.mark.parametrize("ds,expected", [("economy", "economy"), ("sleep", "sleep")])
def test_mode_follows_economy_and_sleep(mode_sensor, ds, expected):
    s, _ = mode_sensor
    assert render(s["state"], {DS: ds}, this=_this()) == expected


def test_standby_display_means_standard(mode_sensor):
    # "St" (labelled standby by the firmware) is shown when Standard is selected.
    s, _ = mode_sensor
    assert render(s["state"], {DS: "standby"}, this=_this("economy", NOW)) == "standard"


def test_latch_holds_economy_while_display_alternates(mode_sensor):
    s, _ = mode_sensor
    seen = NOW - timedelta(seconds=5)
    assert render(s["state"], {DS: "temperature"}, this=_this("economy", seen)) == "economy"
    assert render(s["state"], {DS: "blank"}, this=_this("economy", seen)) == "economy"


def test_latch_decays_after_ten_minutes_without_economy(mode_sensor):
    # Covers a missed "St" frame, e.g. a power cycle that resets the mode.
    s, _ = mode_sensor
    seen = NOW - timedelta(minutes=11)
    assert render(s["state"], {DS: "temperature"}, this=_this("economy", seen)) == "standard"


def test_temperature_display_from_standard_stays_standard(mode_sensor):
    s, _ = mode_sensor
    assert render(s["state"], {DS: "temperature"}, this=_this("standard", NOW)) == "standard"


def test_first_render_without_history_is_standard(mode_sensor):
    s, _ = mode_sensor
    fresh = SimpleNamespace(state="unknown", attributes={})
    assert render(s["state"], {DS: "temperature"}, this=fresh) == "standard"


def test_mode_seen_refreshes_on_economy_and_holds_otherwise(mode_sensor):
    s, _ = mode_sensor
    tpl = s["attributes"]["mode_seen"]
    assert render(tpl, {DS: "economy"}, this=_this()) == NOW.isoformat()
    old = NOW - timedelta(minutes=3)
    assert render(tpl, {DS: "temperature"}, this=_this("economy", old)) == old.isoformat()


# --- panel mode alert --------------------------------------------------------


def test_mode_alert_triggers(mode_alert):
    by_id = {t["id"]: t for t in mode_alert["trigger"]}
    entered = by_id["entered"]
    assert entered["entity_id"] == "sensor.hot_tub_panel_mode"
    assert set(entered["to"]) == {"economy", "sleep"}
    assert entered["for"] == {"minutes": 2}, "ignore the seconds-long pass through Ec/SL while cycling modes"
    cleared = by_id["cleared"]
    assert cleared["to"] == "standard"
    assert set(cleared["from"]) == {"economy", "sleep"}


def _branch(auto, trigger_id):
    choose = next(item["choose"] for item in auto["action"] if "choose" in item)
    return next(b["sequence"] for b in choose
                if any(c.get("id") == trigger_id for c in b["conditions"]))


def test_mode_alert_entered_pushes_with_the_fix(mode_alert):
    seq = _branch(mode_alert, "entered")
    actions = [a.get("action") for a in seq]
    assert "persistent_notification.create" in actions
    push = next(a for a in seq if str(a.get("action", "")).startswith("notify.mobile_app"))
    text = push["data"]["message"]
    assert "Light" in text and "St" in text, "the push should say how to get back to Standard"


def test_mode_alert_cleared_dismisses(mode_alert):
    seq = _branch(mode_alert, "cleared")
    dismiss = next(a for a in seq if a.get("action") == "persistent_notification.dismiss")
    create = next(a for a in _branch(mode_alert, "entered")
                  if a.get("action") == "persistent_notification.create")
    assert dismiss["data"]["notification_id"] == create["data"]["notification_id"]


# --- heat start guard --------------------------------------------------------

SP = "number.tublemetry_hot_tub_setpoint"
WATER = "sensor.hot_tub_water_temperature"


def test_guard_triggers_on_confirmed_setpoint(guard):
    (trig,) = guard["trigger"]
    assert trig["entity_id"] == SP
    assert set(trig["not_from"]) == {"unknown", "unavailable"}
    assert set(trig["not_to"]) == {"unknown", "unavailable"}
    assert guard["mode"] == "restart", "a newer raise must restart the 10-min wait"


def _trigger(frm: str, to: str):
    return SimpleNamespace(from_state=SimpleNamespace(state=frm), to_state=SimpleNamespace(state=to))


def _conditions_pass(guard, frm, to, water_obj, states=None) -> bool:
    states = {"binary_sensor.tublemetry_hot_tub_api_status": "on", **(states or {})}
    for cond in guard["condition"]:
        if cond["condition"] == "template":
            out = render(cond["value_template"], states, {WATER: water_obj} if water_obj else {},
                         trigger=_trigger(frm, to))
            if out != "True":
                return False
        elif cond["condition"] == "state":
            if states.get(cond["entity_id"], "unknown") != cond["state"]:
                return False
        else:
            raise AssertionError(f"unexpected condition type {cond['condition']}")
    return True


def test_guard_arms_on_raise_with_cold_water(guard):
    assert _conditions_pass(guard, "90.0", "104.0", _state("98"))


def test_guard_ignores_a_drop(guard):
    assert not _conditions_pass(guard, "104.0", "90.0", _state("98"))


def test_guard_ignores_raise_when_water_already_hot(guard):
    # 102 -> 104 with fresh 104 water: no heat demand, pump correctly stays off.
    assert not _conditions_pass(guard, "102.0", "104.0", _state("104"))


def test_guard_arms_when_water_reading_is_stale(guard):
    # 2026-11-06: the last reading was 105 from 21:28 the night before; the real
    # water was ~98 by 04:30. A stale reading must not suppress the guard.
    stale = _state("105", last_reported=NOW - timedelta(hours=7))
    assert _conditions_pass(guard, "90.0", "104.0", stale)


def test_guard_arms_when_water_unknown(guard):
    assert _conditions_pass(guard, "90.0", "104.0", _state("unknown"))
    assert _conditions_pass(guard, "90.0", "104.0", None)


def test_guard_skips_when_esp32_offline(guard):
    assert not _conditions_pass(guard, "90.0", "104.0", _state("98"),
                                {"binary_sensor.tublemetry_hot_tub_api_status": "off"})


def test_guard_waits_ten_minutes_for_pump_or_heater(guard):
    wait = next(a for a in guard["action"] if "wait_template" in a)
    assert wait["timeout"] == "00:10:00"
    assert wait["continue_on_timeout"] is True
    tpl = wait["wait_template"]
    assert render(tpl, {"binary_sensor.tublemetry_hot_tub_pump": "on"}) == "True"
    assert render(tpl, {"binary_sensor.tublemetry_hot_tub_heater": "on"}) == "True"
    assert render(tpl, {"binary_sensor.tublemetry_hot_tub_pump": "off",
                        "binary_sensor.tublemetry_hot_tub_heater": "off"}) == "False"


def test_guard_alerts_only_on_timeout(guard):
    idx_wait = next(i for i, a in enumerate(guard["action"]) if "wait_template" in a)
    gate = guard["action"][idx_wait + 1]
    assert gate["condition"] == "template"
    assert render(gate["value_template"], wait=SimpleNamespace(completed=False)) == "True"
    assert render(gate["value_template"], wait=SimpleNamespace(completed=True)) == "False"
    rest = [a.get("action") for a in guard["action"][idx_wait + 2:]]
    assert "persistent_notification.create" in rest
    assert any(a and a.startswith("notify.mobile_app") for a in rest)


# --- the fix sequence ---------------------------------------------------------
# One short line, word for word in every notification that asks the user to
# leave Economy/Sleep, so it reads the same on the lock screen every time.
# Matches what worked on 2026-11-06 (display stepped Ec -> SL -> St).

FIX = "Fix: press Warm, then Light. Tap Light until St shows, then wait."


def _messages(seq):
    return [a["data"]["message"] for a in seq
            if a.get("action") in ("persistent_notification.create",)
            or str(a.get("action", "")).startswith("notify.mobile_app")]


def test_mode_alert_messages_carry_the_fix(mode_alert):
    msgs = _messages(_branch(mode_alert, "entered"))
    assert len(msgs) == 2
    for m in msgs:
        assert FIX in render(m, {"sensor.hot_tub_panel_mode": "economy"})


def _guard_pushes(guard):
    return [a for a in guard["action"]
            if a.get("action") == "persistent_notification.create"
            or str(a.get("action", "")).startswith("notify.mobile_app")]


@pytest.mark.parametrize("mode", ["economy", "sleep"])
def test_not_heating_push_carries_the_fix_when_panel_mode_is_wrong(guard, mode):
    for a in _guard_pushes(guard):
        out = render(a["data"]["message"], {"sensor.hot_tub_panel_mode": mode,
                                            "number.tublemetry_hot_tub_setpoint": "104.0"})
        assert FIX in out


def test_not_heating_push_omits_the_fix_in_standard_mode(guard):
    # In Standard the cause is something else (heater fault, bad decode); a mode
    # fix would send the user to the wrong buttons.
    for a in _guard_pushes(guard):
        out = render(a["data"]["message"], {"sensor.hot_tub_panel_mode": "standard",
                                            "number.tublemetry_hot_tub_setpoint": "104.0"})
        assert FIX not in out
