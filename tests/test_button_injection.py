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

# Retry constants (mirrors C++ values)
MAX_RETRIES = 3
BACKOFF_TABLE = [5000, 15000, 45000]  # ms: 5s, 15s, 45s per D-03


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
    RETRYING = "retrying"
    COOLDOWN = "cooldown"


class InjectorResult:
    NONE = "none"
    SUCCESS = "success"
    TIMEOUT = "timeout"
    ABORTED = "aborted"
    FAILED = "failed"
    BUDGET_EXCEEDED = "budget_exceeded"


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

        # Retry state
        self.retry_count = 0
        self.max_retries = MAX_RETRIES
        self.retry_backoff_ms = 0

        # Press budget (D-06)
        self.press_budget = 0
        self.presses_consumed = 0

        # Result sensor
        self.last_command_result = InjectorResult.NONE

        # Deferred setpoint publish (D-14)
        self.pending_target = None
        self.last_confirmed_setpoint = None
        self.published_setpoint = None

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
        self.retry_count = 0
        self.presses_consumed = 0

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
        self.press_budget = abs(delta) + 2  # D-06: N+2 budget
        self.presses_consumed = 0
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
                self.last_command_result = InjectorResult.SUCCESS
                self.known_setpoint = self.target_temp
                self.last_confirmed_setpoint = self.target_temp
                self.published_setpoint = self.target_temp
                self._transition(InjectorPhase.COOLDOWN)

    def press_once(self):
        """Simulate a raw test press. Invalidates cached setpoint."""
        self.known_setpoint = None  # real setpoint changed — probe on next request

    def timeout(self):
        """Simulate verification timeout. Routes through retry logic."""
        if self.phase == InjectorPhase.VERIFYING:
            self.known_setpoint = None  # don't know where setpoint landed
            if self.retry_count < self.max_retries:
                self.retry_count += 1
                self.retry_backoff_ms = BACKOFF_TABLE[self.retry_count - 1]
                self.last_result = InjectorResult.TIMEOUT
                self._transition(InjectorPhase.RETRYING)
            else:
                self.last_result = InjectorResult.TIMEOUT
                self.last_command_result = InjectorResult.FAILED
                self.known_setpoint = None
                # D-14: Revert setpoint on FAILED
                if self.published_setpoint is not None or self.last_confirmed_setpoint is not None:
                    self.published_setpoint = self.last_confirmed_setpoint
                self._transition(InjectorPhase.COOLDOWN)

    def abort(self):
        """Abort the current sequence."""
        if self.phase != InjectorPhase.IDLE:
            self.last_result = InjectorResult.ABORTED
            self.known_setpoint = None  # don't know where setpoint landed — probe next time
            self._transition(InjectorPhase.COOLDOWN)

    def budget_exceeded(self):
        """Simulate press budget exceeded during ADJUSTING.

        Budget exceeded follows the same retry flow as timeout (D-07).
        If retries remain, transition to RETRYING. If exhausted, FAILED.
        """
        if self.phase == InjectorPhase.ADJUSTING:
            self.known_setpoint = None
            if self.retry_count < self.max_retries:
                self.retry_count += 1
                self.retry_backoff_ms = BACKOFF_TABLE[self.retry_count - 1]
                self.last_result = InjectorResult.BUDGET_EXCEEDED
                self._transition(InjectorPhase.RETRYING)
            else:
                self.last_result = InjectorResult.BUDGET_EXCEEDED
                self.last_command_result = InjectorResult.FAILED
                if self.published_setpoint is not None or self.last_confirmed_setpoint is not None:
                    self.published_setpoint = self.last_confirmed_setpoint
                self._transition(InjectorPhase.COOLDOWN)

    def complete_retrying(self):
        """Simulate backoff elapsed, transition from RETRYING to PROBING.

        D-01: Always re-probe from scratch -- invalidate cache.
        """
        assert self.phase == InjectorPhase.RETRYING
        self.known_setpoint = None  # D-01: invalidate cache
        self._transition(InjectorPhase.PROBING)

    def control_setpoint(self, value: float) -> bool:
        """Simulate TublemetrySetpoint.control() -- deferred publish (D-14).

        Stores pending_target, does NOT set published_setpoint.
        Calls request_temperature internally.
        """
        self.pending_target = value
        self.last_confirmed_setpoint = self.published_setpoint
        return self.request_temperature(value)

    def finish_sequence_result(self, result: str):
        """Apply final result to published_setpoint.

        On SUCCESS: published_setpoint = target_temp.
        On FAILED: published_setpoint = last_confirmed_setpoint.
        """
        if result == InjectorResult.SUCCESS:
            self.published_setpoint = self.target_temp
            self.last_confirmed_setpoint = self.target_temp
        elif result == InjectorResult.FAILED:
            self.published_setpoint = self.last_confirmed_setpoint

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
        """First timeout with retries remaining goes to RETRYING (not COOLDOWN)."""
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        inj.run_to_verify()
        inj.timeout()
        assert inj.last_result == InjectorResult.TIMEOUT
        assert inj.phase == InjectorPhase.RETRYING

    def test_timeout_does_not_cache_setpoint(self):
        """Timeout clears known_setpoint — setpoint location is uncertain after failed sequence."""
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        inj.run_to_verify()
        inj.timeout()
        assert inj.known_setpoint is None  # cleared: must probe on next request

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


class TestSetpointInvalidation:
    """known_setpoint must be cleared whenever the real setpoint may have drifted."""

    def test_press_once_invalidates_known_setpoint(self):
        """Test press changes the real setpoint — next request must probe."""
        inj = SimulatedInjector()
        inj.known_setpoint = 102.0
        inj.press_once()
        assert inj.known_setpoint is None

    def test_next_sequence_after_press_once_probes(self):
        """After a test press, the next request goes to PROBING not ADJUSTING."""
        inj = SimulatedInjector()
        inj.known_setpoint = 102.0
        inj.press_once()
        inj.request_temperature(104.0)
        assert inj.phase == InjectorPhase.PROBING

    def test_timeout_invalidates_known_setpoint(self):
        """Verification timeout means we don't know where the setpoint landed."""
        inj = SimulatedInjector()
        inj.known_setpoint = 102.0
        inj.request_temperature(104.0)
        inj.run_to_verify()
        inj.timeout()
        assert inj.known_setpoint is None

    def test_next_sequence_after_timeout_probes(self):
        """After all retries exhausted and cooldown, next request probes (stale cache cleared)."""
        inj = SimulatedInjector()
        inj.known_setpoint = 102.0
        inj.request_temperature(104.0)
        # Exhaust all retries
        for _ in range(3):
            inj.run_to_verify()
            inj.timeout()
            inj.complete_retrying()
            inj.complete_probe(102)
        # 4th attempt times out -> FAILED -> COOLDOWN
        inj.run_to_verify()
        inj.timeout()
        assert inj.phase == InjectorPhase.COOLDOWN
        inj.finish_cooldown()
        inj.request_temperature(104.0)
        assert inj.phase == InjectorPhase.PROBING

    def test_abort_invalidates_known_setpoint(self):
        """Aborted sequence means we don't know where the setpoint landed."""
        inj = SimulatedInjector()
        inj.known_setpoint = 102.0
        inj.request_temperature(104.0)
        inj.abort()
        assert inj.known_setpoint is None

    def test_success_still_caches_setpoint(self):
        """Success must still cache the confirmed setpoint (regression guard)."""
        inj = SimulatedInjector()
        inj.request_temperature(100.0)
        inj.complete_probe(98.0)
        inj.run_to_verify()
        inj.feed_temperature(100.0)
        assert inj.known_setpoint == 100.0


class TestRetryLogic:
    """Test retry state machine transitions."""

    def test_timeout_with_retries_remaining_goes_to_retrying(self):
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        inj.run_to_verify()
        inj.timeout()
        assert inj.phase == InjectorPhase.RETRYING
        assert inj.retry_count == 1

    def test_retry_transitions_to_probing(self):
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        inj.run_to_verify()
        inj.timeout()
        assert inj.phase == InjectorPhase.RETRYING
        inj.complete_retrying()
        assert inj.phase == InjectorPhase.PROBING

    def test_retry_invalidates_cache(self):
        """D-01: After complete_retrying(), known_setpoint must be None."""
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        inj.run_to_verify()
        inj.timeout()
        inj.complete_retrying()
        assert inj.known_setpoint is None

    def test_full_retry_then_success(self):
        """timeout -> RETRYING -> complete_retrying -> PROBING -> complete_probe -> ADJUSTING -> verify -> SUCCESS."""
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        inj.run_to_verify()
        inj.timeout()
        assert inj.phase == InjectorPhase.RETRYING
        inj.complete_retrying()
        assert inj.phase == InjectorPhase.PROBING
        inj.complete_probe(95)
        assert inj.phase == InjectorPhase.ADJUSTING
        inj.run_to_verify()
        inj.feed_temperature(100)
        assert inj.phase == InjectorPhase.COOLDOWN
        assert inj.last_result == InjectorResult.SUCCESS

    def test_retry_preserves_target(self):
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        inj.run_to_verify()
        inj.timeout()
        assert inj.target_temp == 100

    def test_multiple_retries_increment_count(self):
        """3 successive timeouts produce retry_count 1, 2, 3."""
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)

        for expected_count in [1, 2, 3]:
            inj.run_to_verify()
            inj.timeout()
            assert inj.retry_count == expected_count
            if expected_count < 3:
                inj.complete_retrying()
                inj.complete_probe(95)


class TestRetryBackoff:
    """Test exponential backoff timing between retries."""

    def test_first_retry_backoff_5000ms(self):
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        inj.run_to_verify()
        inj.timeout()
        assert inj.retry_backoff_ms == 5000

    def test_second_retry_backoff_15000ms(self):
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        inj.run_to_verify()
        inj.timeout()
        inj.complete_retrying()
        inj.complete_probe(95)
        inj.run_to_verify()
        inj.timeout()
        assert inj.retry_backoff_ms == 15000

    def test_third_retry_backoff_45000ms(self):
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        # Retry 1
        inj.run_to_verify()
        inj.timeout()
        inj.complete_retrying()
        inj.complete_probe(95)
        # Retry 2
        inj.run_to_verify()
        inj.timeout()
        inj.complete_retrying()
        inj.complete_probe(95)
        # Retry 3
        inj.run_to_verify()
        inj.timeout()
        assert inj.retry_backoff_ms == 45000


class TestRetryExhaustion:
    """Test behavior when all retries are exhausted."""

    def test_three_retries_then_failed(self):
        """3 timeouts + 4th timeout -> COOLDOWN with FAILED."""
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        # 3 retries
        for _ in range(3):
            inj.run_to_verify()
            inj.timeout()
            inj.complete_retrying()
            inj.complete_probe(95)
        # 4th attempt times out -> FAILED
        inj.run_to_verify()
        inj.timeout()
        assert inj.phase == InjectorPhase.COOLDOWN
        assert inj.last_command_result == InjectorResult.FAILED

    def test_failed_clears_known_setpoint(self):
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        for _ in range(3):
            inj.run_to_verify()
            inj.timeout()
            inj.complete_retrying()
            inj.complete_probe(95)
        inj.run_to_verify()
        inj.timeout()
        assert inj.known_setpoint is None

    def test_failed_distinct_from_timeout(self):
        """last_command_result after exhaustion is 'failed', not 'timeout'."""
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        for _ in range(3):
            inj.run_to_verify()
            inj.timeout()
            inj.complete_retrying()
            inj.complete_probe(95)
        inj.run_to_verify()
        inj.timeout()
        assert inj.last_command_result == InjectorResult.FAILED
        assert inj.last_command_result != InjectorResult.TIMEOUT

    def test_retry_count_is_three_on_exhaustion(self):
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        for _ in range(3):
            inj.run_to_verify()
            inj.timeout()
            inj.complete_retrying()
            inj.complete_probe(95)
        inj.run_to_verify()
        inj.timeout()
        assert inj.retry_count == 3


class TestPressBudget:
    """Test press budget calculation and enforcement."""

    def test_budget_calculated_as_n_plus_2(self):
        """For delta=5, press_budget=7."""
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        assert inj.press_budget == 7  # abs(100-95) + 2

    def test_budget_for_delta_1(self):
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(96)
        assert inj.press_budget == 3  # abs(96-95) + 2

    def test_budget_for_delta_0(self):
        """No ADJUSTING phase (skip to VERIFYING), budget irrelevant."""
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(95)
        assert inj.phase == InjectorPhase.VERIFYING
        # Budget stays at 0 since _start_adjusting skips for delta 0
        assert inj.press_budget == 0

    def test_budget_exceeded_aborts_attempt(self):
        """Simulate presses_consumed > press_budget -> triggers retry path."""
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        assert inj.phase == InjectorPhase.ADJUSTING
        assert inj.press_budget == 7
        # Simulate exceeding budget
        inj.presses_consumed = 8
        inj.budget_exceeded()
        assert inj.phase == InjectorPhase.RETRYING

    def test_budget_resets_on_retry(self):
        """After retry and re-probe, budget recalculated from fresh delta."""
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        assert inj.press_budget == 7
        inj.presses_consumed = 8
        inj.budget_exceeded()
        inj.complete_retrying()
        # Re-probe reveals 97 this time (different from original 95)
        inj.complete_probe(97)
        assert inj.press_budget == 5  # abs(100-97) + 2


class TestBudgetExceededRetry:
    """Test that budget exceeded follows retry flow."""

    def test_budget_exceeded_goes_to_retrying(self):
        """budget_exceeded() transitions to RETRYING when retries remain."""
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        inj.presses_consumed = 8
        inj.budget_exceeded()
        assert inj.phase == InjectorPhase.RETRYING
        assert inj.retry_count == 1

    def test_budget_exceeded_with_no_retries_left_fails(self):
        """budget_exceeded() when retry_count >= max_retries -> FAILED."""
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        inj.retry_count = 3  # All retries used
        inj.presses_consumed = 8
        inj.budget_exceeded()
        assert inj.phase == InjectorPhase.COOLDOWN
        assert inj.last_command_result == InjectorResult.FAILED

    def test_budget_exceeded_increments_retry_count(self):
        """budget_exceeded follows same retry counting as timeout."""
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        assert inj.retry_count == 0
        inj.presses_consumed = 8
        inj.budget_exceeded()
        assert inj.retry_count == 1


class TestResultSensors:
    """Test result sensor values through the sequence lifecycle."""

    def test_initial_result_is_none(self):
        inj = SimulatedInjector()
        assert inj.last_command_result == InjectorResult.NONE

    def test_success_result(self):
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        inj.run_to_verify()
        inj.feed_temperature(100)
        assert inj.last_command_result == InjectorResult.SUCCESS

    def test_timeout_result_during_retry(self):
        """After timeout (retries remain), last_result is TIMEOUT."""
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        inj.run_to_verify()
        inj.timeout()
        assert inj.last_result == InjectorResult.TIMEOUT

    def test_failed_result(self):
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        for _ in range(3):
            inj.run_to_verify()
            inj.timeout()
            inj.complete_retrying()
            inj.complete_probe(95)
        inj.run_to_verify()
        inj.timeout()
        assert inj.last_command_result == InjectorResult.FAILED

    def test_retry_count_published_on_retry(self):
        """retry_count increments and is accessible."""
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        inj.run_to_verify()
        inj.timeout()
        assert inj.retry_count == 1
        inj.complete_retrying()
        inj.complete_probe(95)
        inj.run_to_verify()
        inj.timeout()
        assert inj.retry_count == 2


class TestDeferredSetpoint:
    """Test deferred setpoint publish pattern (D-14)."""

    def test_control_does_not_publish_immediately(self):
        """control_setpoint(100) -> published_setpoint is NOT 100."""
        inj = SimulatedInjector()
        inj.published_setpoint = 95.0
        inj.known_setpoint = 95.0
        inj.control_setpoint(100)
        assert inj.published_setpoint != 100
        assert inj.published_setpoint == 95.0

    def test_success_publishes_confirmed(self):
        """After full successful sequence, published_setpoint == target."""
        inj = SimulatedInjector()
        inj.published_setpoint = 95.0
        inj.known_setpoint = 95.0
        inj.control_setpoint(100)
        inj.run_to_verify()
        inj.feed_temperature(100)
        assert inj.published_setpoint == 100

    def test_failed_reverts_setpoint(self):
        """control_setpoint(100) from known 95. Exhaust retries -> published_setpoint == 95."""
        inj = SimulatedInjector()
        inj.published_setpoint = 95.0
        inj.known_setpoint = 95.0
        inj.control_setpoint(100)
        assert inj.last_confirmed_setpoint == 95.0
        # Exhaust all retries
        for _ in range(3):
            inj.run_to_verify()
            inj.timeout()
            inj.complete_retrying()
            inj.complete_probe(95)
        inj.run_to_verify()
        inj.timeout()
        assert inj.published_setpoint == 95.0

    def test_last_confirmed_setpoint_updated_on_success(self):
        """After SUCCESS, last_confirmed_setpoint == target."""
        inj = SimulatedInjector()
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        inj.run_to_verify()
        inj.feed_temperature(100)
        assert inj.last_confirmed_setpoint == 100

    def test_rejected_request_keeps_current(self):
        """If request_temperature returns False (busy), published_setpoint unchanged."""
        inj = SimulatedInjector()
        inj.published_setpoint = 95.0
        inj.known_setpoint = 95.0
        inj.request_temperature(100)
        # Now busy -- second request rejected
        result = inj.control_setpoint(104)
        assert result is False
        assert inj.published_setpoint == 95.0


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

    def test_no_climate_entity(self, yaml_config):
        """Architecture uses number entity, not climate entity.

        Climate entity was removed in plan 02-01 and replaced with
        number.tublemetry_hot_tub_setpoint for direct setpoint control.
        """
        climates = yaml_config.get("climate", [])
        assert len(climates) == 0, (
            "climate entity must not be present — architecture uses number entity. "
            "Use number.tublemetry_hot_tub_setpoint for setpoint control."
        )
