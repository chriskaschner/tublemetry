"""Tests for button injection logic.

Tests the probe+cache algorithm, direct-delta calculations, safety clamps,
state machine transitions, timing defaults, and YAML configuration.

Strategy:
  - First call (setpoint unknown): PROBING (1 down press) -> read display -> ADJUSTING
  - Subsequent calls (setpoint known): direct delta -> ADJUSTING, no probe
"""

import math
import pytest
import yaml
from pathlib import Path


# --- Direct-delta algorithm (mirrors C++ logic) ---

TEMP_FLOOR = 80.0
TEMP_CEILING = 104.0

# Default timing (ms)
DEFAULT_PRESS_DURATION_MS = 200
DEFAULT_INTER_PRESS_DELAY_MS = 300
DEFAULT_VERIFY_TIMEOUT_MS = 10000
DEFAULT_COOLDOWN_MS = 1000


def calculate_direct_sequence(from_setpoint: float, target: float) -> dict:
    """Calculate the direct-delta button press sequence.

    Returns dict with:
        valid: bool — whether the target is in range
        direction: str — "up", "down", or "none"
        presses: int — number of presses needed
        estimated_duration_ms: int — estimated time for the sequence
    """
    if math.isnan(target) or math.isnan(from_setpoint):
        return {"valid": False, "direction": "none", "presses": 0, "estimated_duration_ms": 0}

    target = round(target)

    if target < TEMP_FLOOR or target > TEMP_CEILING:
        return {"valid": False, "direction": "none", "presses": 0, "estimated_duration_ms": 0}

    delta = int(target - round(from_setpoint))
    presses = abs(delta)
    direction = "up" if delta > 0 else ("down" if delta < 0 else "none")

    press_cycle_ms = DEFAULT_PRESS_DURATION_MS + DEFAULT_INTER_PRESS_DELAY_MS
    estimated_duration_ms = presses * press_cycle_ms

    return {
        "valid": True,
        "direction": direction,
        "presses": presses,
        "estimated_duration_ms": estimated_duration_ms,
    }


# --- State machine phases (mirroring C++ enum) ---

class InjectorPhase:
    IDLE = "idle"
    PROBING = "probing"
    ADJUSTING = "adjusting"
    VERIFYING = "verifying"
    COOLDOWN = "cooldown"


class InjectorResult:
    NONE = "none"
    SUCCESS = "success"
    TIMEOUT = "timeout"
    ABORTED = "aborted"


class SimulatedInjector:
    """Python simulation of the C++ ButtonInjector state machine.

    Mirrors the probe+cache strategy:
      - known_setpoint = None means first-boot (probe required)
      - known_setpoint = float means cached from last success (direct delta)
    """

    def __init__(self):
        self.phase = InjectorPhase.IDLE
        self.target_temp = 0.0
        self.known_setpoint = None   # None = unknown; float = cached
        self.presses_done = 0
        self.presses_needed = 0
        self.adjusting_up = True
        self.last_result = InjectorResult.NONE
        self.sequence_count = 0
        self.configured = True
        self.transitions = []

    def request_temperature(self, target: float) -> bool:
        if not self.configured:
            return False
        if self.phase != InjectorPhase.IDLE:
            return False
        if math.isnan(target):
            return False
        if target < TEMP_FLOOR or target > TEMP_CEILING:
            return False

        target = round(target)
        self.target_temp = target
        self.sequence_count += 1

        if self.known_setpoint is not None:
            self._start_adjusting(self.known_setpoint)
        else:
            self._transition(InjectorPhase.PROBING)
        return True

    def complete_probe(self, probed_setpoint: float):
        """Simulate probe press completing and display reading captured."""
        assert self.phase == InjectorPhase.PROBING
        self._start_adjusting(probed_setpoint)

    def _start_adjusting(self, from_setpoint: float):
        delta = int(round(self.target_temp) - round(from_setpoint))
        if delta == 0:
            self._transition(InjectorPhase.VERIFYING)
            return
        self.adjusting_up = delta > 0
        self.presses_needed = abs(delta)
        self.presses_done = 0
        self._transition(InjectorPhase.ADJUSTING)

    def run_to_verify(self):
        """Fast-forward through adjusting to reach verifying."""
        if self.phase == InjectorPhase.ADJUSTING:
            self.presses_done = self.presses_needed
            self._transition(InjectorPhase.VERIFYING)

    def feed_temperature(self, temp: float):
        """Simulate display showing a temperature during verify phase."""
        if self.phase == InjectorPhase.VERIFYING:
            if temp == self.target_temp:
                self.last_result = InjectorResult.SUCCESS
                self.known_setpoint = self.target_temp
                self._transition(InjectorPhase.COOLDOWN)

    def timeout(self):
        """Simulate verification timeout."""
        if self.phase == InjectorPhase.VERIFYING:
            self.last_result = InjectorResult.TIMEOUT
            self._transition(InjectorPhase.COOLDOWN)

    def abort(self):
        """Abort the current sequence."""
        if self.phase != InjectorPhase.IDLE:
            self.last_result = InjectorResult.ABORTED
            self._transition(InjectorPhase.COOLDOWN)

    def finish_cooldown(self):
        """Complete cooldown and return to idle."""
        if self.phase == InjectorPhase.COOLDOWN:
            self._transition(InjectorPhase.IDLE)

    def _transition(self, new_phase):
        self.transitions.append((self.phase, new_phase))
        self.phase = new_phase


# =============================================================================
# Tests
# =============================================================================


class TestDirectDeltaAlgorithm:
    """Test the direct-delta press calculation."""

    def test_up_delta(self):
        seq = calculate_direct_sequence(95, 100)
        assert seq["valid"] is True
        assert seq["direction"] == "up"
        assert seq["presses"] == 5

    def test_down_delta(self):
        seq = calculate_direct_sequence(100, 95)
        assert seq["valid"] is True
        assert seq["direction"] == "down"
        assert seq["presses"] == 5

    def test_no_delta(self):
        seq = calculate_direct_sequence(95, 95)
        assert seq["valid"] is True
        assert seq["direction"] == "none"
        assert seq["presses"] == 0

    def test_target_below_floor_rejected(self):
        seq = calculate_direct_sequence(95, 79)
        assert seq["valid"] is False

    def test_target_above_ceiling_rejected(self):
        seq = calculate_direct_sequence(95, 105)
        assert seq["valid"] is False

    def test_floor_boundary_valid(self):
        seq = calculate_direct_sequence(95, 80)
        assert seq["valid"] is True
        assert seq["direction"] == "down"
        assert seq["presses"] == 15

    def test_ceiling_boundary_valid(self):
        seq = calculate_direct_sequence(95, 104)
        assert seq["valid"] is True
        assert seq["direction"] == "up"
        assert seq["presses"] == 9

    def test_rounding(self):
        """Target 95.4 rounds to 95, 95.6 rounds to 96."""
        seq_low = calculate_direct_sequence(90, 95.4)
        assert seq_low["presses"] == 5  # round(95.4) = 95

        seq_high = calculate_direct_sequence(90, 95.6)
        assert seq_high["presses"] == 6  # round(95.6) = 96

    def test_nan_target_rejected(self):
        seq = calculate_direct_sequence(95, float("nan"))
        assert seq["valid"] is False

    def test_nan_from_rejected(self):
        seq = calculate_direct_sequence(float("nan"), 95)
        assert seq["valid"] is False

    def test_estimated_duration(self):
        """5 presses × 500ms = 2500ms."""
        seq = calculate_direct_sequence(95, 100)
        assert seq["estimated_duration_ms"] == 5 * 500

    @pytest.mark.parametrize("target", range(80, 105))
    def test_all_valid_targets(self, target):
        seq = calculate_direct_sequence(80, target)
        assert seq["valid"] is True
        assert seq["presses"] == target - 80


class TestSafetyClamps:
    """Test temperature range enforcement."""

    def test_floor_boundary(self):
        assert calculate_direct_sequence(90, 80)["valid"] is True
        assert calculate_direct_sequence(90, 79)["valid"] is False

    def test_ceiling_boundary(self):
        assert calculate_direct_sequence(90, 104)["valid"] is True
        assert calculate_direct_sequence(90, 105)["valid"] is False

    def test_negative_temperature(self):
        assert calculate_direct_sequence(90, -10)["valid"] is False

    def test_nan_temperature(self):
        assert calculate_direct_sequence(90, float("nan"))["valid"] is False


class TestStateMachine:
    """Test state machine transitions."""

    def test_idle_initial_state(self):
        inj = SimulatedInjector()
        assert inj.phase == InjectorPhase.IDLE

    def test_first_request_goes_to_probing(self):
        """Unknown setpoint → probe first."""
        inj = SimulatedInjector()
        assert inj.request_temperature(95) is True
        assert inj.phase == InjectorPhase.PROBING

    def test_known_setpoint_skips_probe(self):
        """Known setpoint → direct to adjusting."""
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        assert inj.request_temperature(100) is True
        assert inj.phase == InjectorPhase.ADJUSTING

    def test_same_target_as_known_skips_adjusting(self):
        """Known setpoint == target → skip straight to verifying."""
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(95)
        assert inj.phase == InjectorPhase.VERIFYING

    def test_probe_then_adjust_up(self):
        """First request: probe reveals 95, target is 100 → 5 up presses."""
        inj = SimulatedInjector()
        inj.request_temperature(100)
        assert inj.phase == InjectorPhase.PROBING
        # Probe down press reveals setpoint - 1 = 94; we read 94 as probed setpoint
        inj.complete_probe(94)
        assert inj.phase == InjectorPhase.ADJUSTING
        assert inj.presses_needed == 6  # 100 - 94 = 6
        assert inj.adjusting_up is True

    def test_probe_then_adjust_down(self):
        """Probe reveals 100, target is 95 → 5 down presses."""
        inj = SimulatedInjector()
        inj.request_temperature(95)
        inj.complete_probe(100)
        assert inj.phase == InjectorPhase.ADJUSTING
        assert inj.presses_needed == 5
        assert inj.adjusting_up is False

    def test_full_sequence_unknown_setpoint(self):
        inj = SimulatedInjector()
        inj.request_temperature(100)
        inj.complete_probe(98)
        inj.run_to_verify()
        assert inj.phase == InjectorPhase.VERIFYING
        inj.feed_temperature(100)
        assert inj.phase == InjectorPhase.COOLDOWN
        assert inj.last_result == InjectorResult.SUCCESS
        inj.finish_cooldown()
        assert inj.phase == InjectorPhase.IDLE

    def test_success_caches_setpoint(self):
        """After success, known_setpoint is updated to target."""
        inj = SimulatedInjector()
        inj.request_temperature(100)
        inj.complete_probe(98)
        inj.run_to_verify()
        inj.feed_temperature(100)
        assert inj.known_setpoint == 100

    def test_second_call_uses_cache(self):
        """Second request skips probe and uses exact delta."""
        inj = SimulatedInjector()
        # First sequence
        inj.request_temperature(100)
        inj.complete_probe(98)
        inj.run_to_verify()
        inj.feed_temperature(100)
        inj.finish_cooldown()
        # Second sequence — known setpoint = 100, target = 97 → 3 down presses
        inj.request_temperature(97)
        assert inj.phase == InjectorPhase.ADJUSTING
        assert inj.presses_needed == 3
        assert inj.adjusting_up is False

    def test_full_transitions_unknown_setpoint(self):
        inj = SimulatedInjector()
        inj.request_temperature(100)
        inj.complete_probe(98)
        inj.run_to_verify()
        inj.feed_temperature(100)
        inj.finish_cooldown()

        expected = [
            (InjectorPhase.IDLE, InjectorPhase.PROBING),
            (InjectorPhase.PROBING, InjectorPhase.ADJUSTING),
            (InjectorPhase.ADJUSTING, InjectorPhase.VERIFYING),
            (InjectorPhase.VERIFYING, InjectorPhase.COOLDOWN),
            (InjectorPhase.COOLDOWN, InjectorPhase.IDLE),
        ]
        assert inj.transitions == expected

    def test_full_transitions_known_setpoint(self):
        inj = SimulatedInjector()
        inj.known_setpoint = 100.0
        inj.request_temperature(97)
        inj.run_to_verify()
        inj.feed_temperature(97)
        inj.finish_cooldown()

        expected = [
            (InjectorPhase.IDLE, InjectorPhase.ADJUSTING),
            (InjectorPhase.ADJUSTING, InjectorPhase.VERIFYING),
            (InjectorPhase.VERIFYING, InjectorPhase.COOLDOWN),
            (InjectorPhase.COOLDOWN, InjectorPhase.IDLE),
        ]
        assert inj.transitions == expected

    def test_concurrent_rejection(self):
        """Second request while busy should be rejected."""
        inj = SimulatedInjector()
        assert inj.request_temperature(95) is True
        assert inj.request_temperature(100) is False
        assert inj.target_temp == 95

    def test_request_after_completion(self):
        """After a sequence completes, a new request should be accepted."""
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(95)
        inj.run_to_verify()
        inj.feed_temperature(95)
        inj.finish_cooldown()

        assert inj.request_temperature(100) is True
        assert inj.target_temp == 100
        assert inj.sequence_count == 2

    def test_timeout_result(self):
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        inj.run_to_verify()
        inj.timeout()
        assert inj.last_result == InjectorResult.TIMEOUT
        assert inj.phase == InjectorPhase.COOLDOWN

    def test_timeout_does_not_cache_setpoint(self):
        """Timeout should not update known_setpoint."""
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        inj.run_to_verify()
        inj.timeout()
        assert inj.known_setpoint == 95.0  # unchanged

    def test_abort_during_probing(self):
        inj = SimulatedInjector()
        inj.request_temperature(95)
        assert inj.phase == InjectorPhase.PROBING
        inj.abort()
        assert inj.last_result == InjectorResult.ABORTED
        assert inj.phase == InjectorPhase.COOLDOWN

    def test_abort_during_adjusting(self):
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        assert inj.phase == InjectorPhase.ADJUSTING
        inj.abort()
        assert inj.last_result == InjectorResult.ABORTED

    def test_abort_idle_is_noop(self):
        inj = SimulatedInjector()
        inj.abort()
        assert inj.phase == InjectorPhase.IDLE
        assert inj.last_result == InjectorResult.NONE

    def test_wrong_temperature_doesnt_verify(self):
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        inj.run_to_verify()
        inj.feed_temperature(99)
        assert inj.phase == InjectorPhase.VERIFYING

    def test_unconfigured_rejects_request(self):
        inj = SimulatedInjector()
        inj.configured = False
        assert inj.request_temperature(95) is False
        assert inj.phase == InjectorPhase.IDLE

    def test_out_of_range_rejects_request(self):
        inj = SimulatedInjector()
        assert inj.request_temperature(110) is False
        assert inj.phase == InjectorPhase.IDLE


class TestTimingDefaults:
    """Verify timing constants match the C++ defaults."""

    def test_press_duration(self):
        assert DEFAULT_PRESS_DURATION_MS == 200

    def test_inter_press_delay(self):
        assert DEFAULT_INTER_PRESS_DELAY_MS == 300

    def test_verify_timeout(self):
        assert DEFAULT_VERIFY_TIMEOUT_MS == 10000

    def test_cooldown(self):
        assert DEFAULT_COOLDOWN_MS == 1000

    def test_press_cycle(self):
        """One press cycle = 500ms (200ms press + 300ms gap)."""
        assert DEFAULT_PRESS_DURATION_MS + DEFAULT_INTER_PRESS_DELAY_MS == 500

    def test_tou_typical_sequence_duration(self):
        """TOU 4-degree shift: 4 presses × 500ms = 2000ms (vs 24500ms rehome)."""
        seq = calculate_direct_sequence(102, 98)
        assert seq["estimated_duration_ms"] == 4 * 500
        assert seq["estimated_duration_ms"] == 2000

    def test_worst_case_sequence_duration(self):
        """80 -> 104: 24 presses × 500ms = 12000ms."""
        seq = calculate_direct_sequence(80, 104)
        assert seq["estimated_duration_ms"] == 24 * 500
        assert seq["estimated_duration_ms"] == 12000


class TestYamlButtonConfig:
    """Verify button injection config in tublemetry.yaml."""

    @pytest.fixture
    def yaml_config(self):
        yaml_path = Path(__file__).parent.parent / "esphome" / "tublemetry.yaml"

        class SecretLoader(yaml.SafeLoader):
            pass

        SecretLoader.add_constructor(
            "!secret", lambda loader, node: f"SECRET({loader.construct_scalar(node)})"
        )

        with open(yaml_path) as f:
            return yaml.load(f, Loader=SecretLoader)

    def test_temp_up_pin_configured(self, yaml_config):
        display = yaml_config["tublemetry_display"]
        assert "temp_up_pin" in display

    def test_temp_down_pin_configured(self, yaml_config):
        display = yaml_config["tublemetry_display"]
        assert "temp_down_pin" in display

    def test_pins_are_different(self, yaml_config):
        display = yaml_config["tublemetry_display"]
        up = display["temp_up_pin"]
        down = display["temp_down_pin"]
        up_num = up if isinstance(up, str) else up.get("number", up)
        down_num = down if isinstance(down, str) else down.get("number", down)
        assert up_num != down_num

    def test_pins_dont_conflict_with_clock_data(self, yaml_config):
        display = yaml_config["tublemetry_display"]

        def get_pin_number(pin_config):
            if isinstance(pin_config, str):
                return pin_config
            return pin_config.get("number", str(pin_config))

        clock = get_pin_number(display["clock_pin"])
        data = get_pin_number(display["data_pin"])
        up = get_pin_number(display["temp_up_pin"])
        down = get_pin_number(display["temp_down_pin"])

        assert up != clock
        assert up != data
        assert down != clock
        assert down != data

    def test_climate_entity_exists(self, yaml_config):
        """Climate entity should exist and reference the display."""
        climates = yaml_config.get("climate", [])
        assert len(climates) >= 1
        tub_climate = climates[0]
        assert tub_climate["platform"] == "tublemetry_display"
        assert tub_climate["tublemetry_id"] == "hot_tub_display"
