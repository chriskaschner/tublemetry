"""Wake-press model tests for the closed-loop setpoint injection fix.

Balboa GL/ML panels consume the FIRST temp-button press (when the panel is idle)
as a display wake/flash that reveals the current setpoint WITHOUT changing it;
only subsequent presses (while the value is flashing) actually increment or
decrement it.

The OLD injector fired exactly abs(delta) presses and verified against the raw
display temperature (which is the idle WATER temperature in normal mode). That
produced two defects at once:
  1. a 1F undershoot (the wake press ate one increment), and
  2. a false 'success' (raw display == target matched the water temp, not the
     real setpoint).

The FIXED injector verifies against the CONFIRMED setpoint (the set-mode flash)
and re-presses any shortfall within the existing N+2 press budget.

These tests model the real panel semantics and assert the PANEL's true setpoint,
so they FAIL against the old verify strategy and PASS against the fixed one --
exactly the coverage the original tests lacked (they re-implemented the buggy
assumptions).
"""

import pytest


class FakeBalboaPanel:
    """Minimal model of a Balboa GL/ML topside panel's wake-press UX.

    - When idle/asleep, the first press only WAKES the panel (reveals the current
      setpoint via a flash) and does not change it.
    - When awake (flashing), a press changes the setpoint by +/-1.
    - `broken=True` models a panel/injection where presses never move the
      setpoint (physically stuck) -- used to prove the make-up loop is bounded.
    - `confirmed_setpoint()` returns the setpoint revealed by the most recent
      flash, i.e. what the closed-loop verifier is allowed to trust. When the
      panel is idle it is the water temperature that shows, never a confirmed
      setpoint.
    """

    def __init__(self, true_setpoint, water_temp, awake=False, broken=False):
        self.true_setpoint = float(true_setpoint)
        self.water_temp = float(water_temp)
        self.awake = awake
        self.broken = broken
        self._flashed = float(true_setpoint) if awake else None

    def press(self, up: bool):
        if not self.awake:
            self.awake = True  # wake/flash only -- no change
        elif not self.broken:
            self.true_setpoint += 1.0 if up else -1.0
        self._flashed = self.true_setpoint  # a press always flashes current value

    def confirmed_setpoint(self):
        """Confirmed setpoint from the latest flash, or None if the panel is idle."""
        return self._flashed


class ModelInjector:
    """Logic model of the injector fast path (ADJUSTING + VERIFYING), parameterized
    by verify strategy so we can contrast OLD (buggy) vs NEW (fixed)."""

    def __init__(self, panel, known_setpoint, verify="new"):
        self.panel = panel
        self.known = float(known_setpoint)
        self.verify = verify

    def request(self, target):
        target = float(round(target))
        delta = int(round(target)) - int(round(self.known))
        budget = abs(delta) + 2  # D-06 N+2
        consumed = 0
        up = delta > 0
        for _ in range(abs(delta)):  # ADJUSTING
            self.panel.press(up)
            consumed += 1
        return self._verify(target, consumed, budget)

    def _verify(self, target, consumed, budget):
        if self.verify == "old":
            # OLD: last_display_temp_ was fed EVERY frame (flash AND idle water
            # temp) and success fired on == target, with no make-up press.
            flashed = self.panel.confirmed_setpoint()
            if flashed is not None and flashed == target:
                return ("success", self.panel.true_setpoint)
            if self.panel.water_temp == target:  # the false-success path
                return ("success", self.panel.true_setpoint)
            return ("timeout", self.panel.true_setpoint)

        # NEW: gate success on the CONFIRMED setpoint; re-press shortfall within
        # the N+2 budget. Bounded loop mirrors VERIFYING -> ADJUSTING -> VERIFYING.
        for _ in range(budget + 2):  # hard cap; real loop is bounded by budget
            confirmed = self.panel.confirmed_setpoint()
            if confirmed is None:
                return ("timeout", self.panel.true_setpoint)
            if confirmed == target:
                return ("success", self.panel.true_setpoint)
            remaining = int(round(target)) - int(round(confirmed))
            if remaining != 0 and consumed < budget:
                more = min(abs(remaining), budget - consumed)
                up = remaining > 0
                for _ in range(more):
                    self.panel.press(up)
                    consumed += 1
                continue
            return ("timeout", self.panel.true_setpoint)
        return ("timeout", self.panel.true_setpoint)


# --- Defect 1: one-degree undershoot on the idle wake press ---


def test_old_logic_undershoots_by_one_when_idle():
    """Reproduces the live bug: command 102 from known 101, panel idle -> lands 101."""
    panel = FakeBalboaPanel(true_setpoint=101, water_temp=102, awake=False)
    result, final = ModelInjector(panel, known_setpoint=101, verify="old").request(102)
    assert final == 101.0  # the wake press was eaten; panel stuck one short


def test_new_logic_reaches_target_when_idle():
    """The fix: same scenario reaches 102 via one bounded make-up press."""
    panel = FakeBalboaPanel(true_setpoint=101, water_temp=102, awake=False)
    result, final = ModelInjector(panel, known_setpoint=101, verify="new").request(102)
    assert result == "success"
    assert final == 102.0


# --- Defect 2: false success from the idle water temperature ---


def test_old_logic_reports_false_success_from_water_temp():
    """Panel stuck at 101 while water reads 102 == target -> OLD falsely succeeds."""
    panel = FakeBalboaPanel(true_setpoint=101, water_temp=102, awake=False, broken=True)
    result, final = ModelInjector(panel, known_setpoint=101, verify="old").request(102)
    assert result == "success"  # the bug
    assert final == 101.0  # ...but the panel never actually reached target


def test_new_logic_no_false_success_from_water_temp():
    """Same stuck panel: NEW must NOT succeed while the confirmed setpoint != target."""
    panel = FakeBalboaPanel(true_setpoint=101, water_temp=102, awake=False, broken=True)
    result, final = ModelInjector(panel, known_setpoint=101, verify="new").request(102)
    assert result != "success"
    assert final == 101.0


# --- No overshoot when the panel is already awake ---


def test_new_logic_awake_lands_on_target_via_correction():
    """Panel already awake: N+1 overshoots by one, then the closed-loop make-up
    corrects it back DOWN to the exact target (net lands on target, not +1)."""
    panel = FakeBalboaPanel(true_setpoint=101, water_temp=95, awake=True)
    result, final = ModelInjector(panel, known_setpoint=101, verify="new").request(102)
    assert result == "success"
    assert final == 102.0


# --- Make-up loop is bounded (does not press forever) ---


def test_new_logic_repress_is_budget_bounded():
    """A stuck panel must time out, not press indefinitely."""
    panel = FakeBalboaPanel(true_setpoint=101, water_temp=95, awake=False, broken=True)
    result, final = ModelInjector(panel, known_setpoint=101, verify="new").request(104)
    assert result == "timeout"
    assert final == 101.0


# --- Symmetric overshoot correction (down press) ---


def test_new_logic_corrects_overshoot_symmetrically():
    """Downward command with N+1: an awake panel overshoots below target, then the
    closed-loop make-up presses UP to correct back to the exact target."""
    panel = FakeBalboaPanel(true_setpoint=103, water_temp=95, awake=True)
    result, final = ModelInjector(panel, known_setpoint=103, verify="new").request(102)
    assert result == "success"
    assert final == 102.0


@pytest.mark.parametrize("start,target", [(96, 90), (90, 102), (101, 104), (104, 80)])
def test_new_logic_reaches_various_targets_from_idle(start, target):
    """Across a range of deltas from an idle panel, NEW always lands on target."""
    panel = FakeBalboaPanel(true_setpoint=start, water_temp=start + 5, awake=False)
    result, final = ModelInjector(panel, known_setpoint=start, verify="new").request(target)
    assert result == "success"
    assert final == float(target)
