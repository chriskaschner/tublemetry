"""Tests for ButtonInjector REFRESHING phase behavior.

The auto-refresh trigger (TublemetryDisplay loop) was removed because
unsolicited down+up press pairs caused setpoint drift when a press was lost.
The REFRESHING phase itself remains available for manual use.
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


