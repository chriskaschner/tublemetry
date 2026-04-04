"""Tests for auto-refresh setpoint keepalive logic.

Two test classes:
  TestRefreshPhase  — mirrors ButtonInjector REFRESHING phase behavior.
  TestAutoRefresh   — mirrors TublemetryDisplay loop() auto-refresh trigger.
"""

import math
import pytest


# ---------------------------------------------------------------------------
# Mirrors C++ ButtonInjector REFRESHING phase
# ---------------------------------------------------------------------------

class RefreshStateMachine:
    """Python mirror of the ButtonInjector REFRESHING phase.

    refresh() fires two presses: down then up (net zero).
    known_setpoint is never modified by refresh().
    Rejected when busy or not configured.
    """

    def __init__(self, known_setpoint=float('nan'), configured=True):
        self.known_setpoint = known_setpoint
        self.configured = configured
        self.busy = False
        self.press_log = []  # list of 'down' or 'up'

    def refresh(self):
        if not self.configured:
            return False
        if self.busy:
            return False
        self.busy = True
        # Simulate two presses: down then up (net zero)
        self.press_log.append('down')
        self.press_log.append('up')
        self.busy = False
        return True


# ---------------------------------------------------------------------------
# Mirrors TublemetryDisplay loop() auto-refresh trigger
# ---------------------------------------------------------------------------

SET_FORCE_INTERVAL_MS = 300_000  # 5 minutes


class AutoRefreshController:
    """Python mirror of the auto-refresh guard in TublemetryDisplay::loop().

    tick() mirrors the needs_refresh calculation and refresh() call.
    """

    def __init__(self):
        self.detected_setpoint = float('nan')
        self.last_setpoint_capture_ms = 0
        self.refresh_calls = 0

    def on_setpoint_confirmed(self, value, now_ms):
        """Mirror classify_display_state_() confirmation block."""
        self.detected_setpoint = value
        self.last_setpoint_capture_ms = now_ms

    def tick(self, now_ms, injector_busy=False):
        """Mirror the auto-refresh guard in loop().

        Returns True if refresh() would be called, False otherwise.
        """
        needs_refresh = (
            math.isnan(self.detected_setpoint) or
            (self.last_setpoint_capture_ms > 0 and
             now_ms - self.last_setpoint_capture_ms >= SET_FORCE_INTERVAL_MS)
        )
        if needs_refresh and not injector_busy:
            self.refresh_calls += 1
            return True
        return False


# ---------------------------------------------------------------------------
# TestRefreshPhase
# ---------------------------------------------------------------------------

class TestRefreshPhase:
    """Test the REFRESHING phase behavior mirrored by RefreshStateMachine."""

    def test_refresh_fires_down_then_up(self):
        """refresh() should produce exactly [down, up] in that order."""
        sm = RefreshStateMachine()
        result = sm.refresh()
        assert result is True
        assert sm.press_log == ['down', 'up']

    def test_refresh_does_not_clear_known_setpoint(self):
        """After refresh(), known_setpoint must be unchanged."""
        sm = RefreshStateMachine(known_setpoint=100.0)
        sm.refresh()
        assert sm.known_setpoint == 100.0

    def test_refresh_does_not_clear_nan_known_setpoint(self):
        """After refresh() with NaN setpoint, known_setpoint stays NaN."""
        sm = RefreshStateMachine(known_setpoint=float('nan'))
        sm.refresh()
        assert math.isnan(sm.known_setpoint)

    def test_refresh_rejected_when_busy(self):
        """Calling refresh() while busy should be a no-op (returns False)."""
        sm = RefreshStateMachine()
        sm.busy = True
        result = sm.refresh()
        assert result is False
        assert sm.press_log == []  # no presses fired

    def test_refresh_rejected_when_not_configured(self):
        """Calling refresh() with no pins configured should be a no-op."""
        sm = RefreshStateMachine(configured=False)
        result = sm.refresh()
        assert result is False
        assert sm.press_log == []

    def test_refresh_exactly_two_presses(self):
        """refresh() fires exactly 2 presses total."""
        sm = RefreshStateMachine()
        sm.refresh()
        assert len(sm.press_log) == 2

    def test_refresh_second_call_after_first(self):
        """After first refresh completes (not busy), second refresh fires again."""
        sm = RefreshStateMachine()
        sm.refresh()
        sm.refresh()
        assert sm.press_log == ['down', 'up', 'down', 'up']


# ---------------------------------------------------------------------------
# TestAutoRefresh
# ---------------------------------------------------------------------------

class TestAutoRefresh:
    """Test the auto-refresh trigger logic mirrored by AutoRefreshController."""

    def test_refresh_triggered_on_nan_setpoint(self):
        """With detected_setpoint=NaN, needs_refresh=True and refresh fires."""
        ctrl = AutoRefreshController()
        # detected_setpoint is NaN by default
        fired = ctrl.tick(now_ms=1000)
        assert fired is True
        assert ctrl.refresh_calls == 1

    def test_refresh_triggered_after_interval(self):
        """300s after last capture, needs_refresh=True."""
        ctrl = AutoRefreshController()
        ctrl.on_setpoint_confirmed(100.0, now_ms=100)
        # Exactly SET_FORCE_INTERVAL_MS elapsed
        fired = ctrl.tick(now_ms=100 + SET_FORCE_INTERVAL_MS)
        assert fired is True
        assert ctrl.refresh_calls == 1

    def test_refresh_not_triggered_before_interval(self):
        """200s after last capture, needs_refresh=False."""
        ctrl = AutoRefreshController()
        ctrl.on_setpoint_confirmed(100.0, now_ms=100)
        fired = ctrl.tick(now_ms=100 + 200_000)  # 200s, less than 300s
        assert fired is False
        assert ctrl.refresh_calls == 0

    def test_refresh_not_triggered_when_busy(self):
        """injector busy → refresh() not called even when needs_refresh=True."""
        ctrl = AutoRefreshController()
        # NaN setpoint → needs_refresh=True, but injector is busy
        fired = ctrl.tick(now_ms=1000, injector_busy=True)
        assert fired is False
        assert ctrl.refresh_calls == 0

    def test_refresh_not_triggered_when_capture_ms_zero_and_setpoint_known(self):
        """last_capture=0 with a known setpoint → needs_refresh=False.

        This avoids spurious refires immediately after a fresh detection:
        if last_setpoint_capture_ms_ is 0 but detected_setpoint_ is known,
        the condition `last_setpoint_capture_ms_ > 0` is False, so no refresh.
        """
        ctrl = AutoRefreshController()
        ctrl.detected_setpoint = 100.0
        ctrl.last_setpoint_capture_ms = 0  # not yet stamped
        fired = ctrl.tick(now_ms=500_000)  # very old, but capture_ms is 0
        assert fired is False
        assert ctrl.refresh_calls == 0

    def test_last_capture_updated_on_setpoint_confirmation(self):
        """on_setpoint_confirmed() stamps last_setpoint_capture_ms correctly."""
        ctrl = AutoRefreshController()
        ctrl.on_setpoint_confirmed(100.0, now_ms=12345)
        assert ctrl.last_setpoint_capture_ms == 12345
        assert ctrl.detected_setpoint == 100.0

    def test_refresh_not_triggered_just_before_interval(self):
        """One ms before the interval expires, no refresh fires."""
        ctrl = AutoRefreshController()
        ctrl.on_setpoint_confirmed(100.0, now_ms=1)  # non-zero so > 0 guard passes
        fired = ctrl.tick(now_ms=1 + SET_FORCE_INTERVAL_MS - 1)
        assert fired is False

    def test_refresh_triggered_one_ms_after_interval(self):
        """One ms after the interval expires, refresh fires."""
        ctrl = AutoRefreshController()
        ctrl.on_setpoint_confirmed(100.0, now_ms=1)  # non-zero so > 0 guard passes
        fired = ctrl.tick(now_ms=1 + SET_FORCE_INTERVAL_MS + 1)
        assert fired is True

    def test_refresh_calls_accumulate(self):
        """Multiple tick() calls that each need refresh accumulate refresh_calls."""
        ctrl = AutoRefreshController()
        # Each tick with NaN setpoint fires
        ctrl.tick(now_ms=0)
        ctrl.tick(now_ms=100)
        ctrl.tick(now_ms=200)
        assert ctrl.refresh_calls == 3
