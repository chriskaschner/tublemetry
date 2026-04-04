"""Tests for set-mode state machine (Python mirror of C++ classify_display_state_()).

Mirrors the logic in esphome/components/tublemetry_display/tublemetry_display.cpp
using a deterministic Python implementation with injected `now_ms` timestamps.

Blank frames drive set-mode entry and setpoint confirmation.
Temperature frames during set mode are suppressed (not published to temperature sensor).
Second blank confirms and publishes the detected setpoint.
Timeout at SET_MODE_TIMEOUT_MS returns to normal temperature publishing.
"""

import math
import pytest


SET_MODE_TIMEOUT_MS = 2000


class SetModeStateMachine:
    """Python mirror of the C++ set-mode state machine in classify_display_state_().

    The feed() method mirrors the blank/numeric/other branching in C++.
    Returns a tuple (event_type, value):
      - ('temperature', float)  — normal temperature published
      - ('suppressed', float)   — temperature during set mode (not published)
      - ('setpoint', float)     — setpoint confirmed and published
      - ('blank', None)         — blank frame processed
      - ('other', None)         — non-numeric, non-blank display (state string)
    """

    def __init__(self):
        self.in_set_mode = False
        self.last_blank_seen_ms = 0
        self.set_temp_potential = float('nan')
        self.detected_setpoint = float('nan')
        self.published_setpoint = None   # last published setpoint value
        self.published_temperature = None  # last published temperature value
        self.known_setpoint_fed = None   # value fed to button injector

    def feed(self, display_str: str, now_ms: int = 0):
        """Process a display string and update state machine.

        Returns ('temperature', value) | ('suppressed', value) |
                ('setpoint', value) | ('blank', None) | ('other', None)
        """
        stripped = display_str.replace(' ', '')

        if stripped == '':
            # Blank branch — mirrors the `stripped.empty()` block in C++
            self.in_set_mode = True
            self.last_blank_seen_ms = now_ms

            result = ('blank', None)

            # Confirmation blank: if a candidate exists, publish detected setpoint
            if not math.isnan(self.set_temp_potential):
                if (math.isnan(self.detected_setpoint) or
                        self.set_temp_potential != self.detected_setpoint):
                    self.detected_setpoint = self.set_temp_potential
                    self.published_setpoint = self.detected_setpoint
                    self.known_setpoint_fed = self.detected_setpoint
                    result = ('setpoint', self.detected_setpoint)

            self.set_temp_potential = float('nan')
            return result

        # Numeric check — mirrors C++ is_numeric logic
        is_numeric = (len(stripped) >= 2 and stripped.isdigit())

        if is_numeric:
            temp = float(stripped)

            # Check timeout before deciding which branch to take
            if self.in_set_mode and (now_ms - self.last_blank_seen_ms) >= SET_MODE_TIMEOUT_MS:
                self.in_set_mode = False
                self.set_temp_potential = float('nan')

            if self.in_set_mode:
                # Setpoint flash — store candidate, suppress temperature publish
                self.set_temp_potential = temp
                return ('suppressed', temp)
            else:
                # Normal temperature publish
                self.published_temperature = temp
                return ('temperature', temp)

        return ('other', None)


# ---------------------------------------------------------------------------
# TestSetModeEntry
# ---------------------------------------------------------------------------

class TestSetModeEntry:
    """Blank frame enters set mode; second blank without candidate does nothing extra."""

    def test_blank_sets_in_set_mode(self):
        """A blank frame sets in_set_mode to True."""
        sm = SetModeStateMachine()
        assert not sm.in_set_mode
        sm.feed('   ', now_ms=0)   # all spaces → stripped == ''
        assert sm.in_set_mode

    def test_blank_records_timestamp(self):
        """Blank frame records last_blank_seen_ms."""
        sm = SetModeStateMachine()
        sm.feed('   ', now_ms=1000)
        assert sm.last_blank_seen_ms == 1000

    def test_second_blank_without_candidate_does_not_publish_setpoint(self):
        """Second blank with no candidate does not trigger setpoint publish."""
        sm = SetModeStateMachine()
        sm.feed('   ', now_ms=0)   # first blank — enters set mode
        result = sm.feed('   ', now_ms=100)  # second blank — no candidate
        assert result == ('blank', None)
        assert sm.published_setpoint is None

    def test_non_blank_non_numeric_does_not_set_in_set_mode(self):
        """Non-blank, non-numeric string (e.g. 'Ec') does not enter set mode."""
        sm = SetModeStateMachine()
        sm.feed(' Ec', now_ms=0)
        assert not sm.in_set_mode

    def test_non_blank_non_numeric_returns_other(self):
        """Non-blank, non-numeric returns ('other', None)."""
        sm = SetModeStateMachine()
        result = sm.feed(' SL', now_ms=0)
        assert result == ('other', None)

    def test_single_digit_is_not_numeric(self):
        """Single-character stripped strings are not treated as numeric (length < 2)."""
        sm = SetModeStateMachine()
        result = sm.feed(' 5', now_ms=0)
        # '5' stripped is length 1 — not numeric per C++ logic (>= 2 required)
        assert result == ('other', None)
        assert not sm.in_set_mode


# ---------------------------------------------------------------------------
# TestSetModeTimeout
# ---------------------------------------------------------------------------

class TestSetModeTimeout:
    """Timeout exits set mode and resumes normal temperature publishing."""

    def test_temperature_before_timeout_is_suppressed(self):
        """Temperature within timeout window is suppressed (in_set_mode stays True)."""
        sm = SetModeStateMachine()
        sm.feed('   ', now_ms=0)         # blank — enter set mode
        result = sm.feed('100', now_ms=1999)   # temperature before 2000ms timeout
        assert result == ('suppressed', 100.0)

    def test_temperature_at_timeout_boundary_is_suppressed(self):
        """Temperature at exactly SET_MODE_TIMEOUT_MS - 1 is still suppressed."""
        sm = SetModeStateMachine()
        sm.feed('   ', now_ms=0)
        result = sm.feed('100', now_ms=SET_MODE_TIMEOUT_MS - 1)
        assert result == ('suppressed', 100.0)

    def test_temperature_at_timeout_exits_set_mode(self):
        """Temperature at or beyond SET_MODE_TIMEOUT_MS exits set mode."""
        sm = SetModeStateMachine()
        sm.feed('   ', now_ms=0)
        result = sm.feed('100', now_ms=SET_MODE_TIMEOUT_MS)
        # At timeout, in_set_mode is cleared, so temperature is published normally
        assert result == ('temperature', 100.0)
        assert not sm.in_set_mode

    def test_temperature_after_timeout_publishes_normally(self):
        """Temperature well after timeout is published as a normal temperature."""
        sm = SetModeStateMachine()
        sm.feed('   ', now_ms=0)
        result = sm.feed('102', now_ms=5000)
        assert result == ('temperature', 102.0)

    def test_timeout_clears_candidate(self):
        """Timeout also clears any accumulated candidate."""
        sm = SetModeStateMachine()
        sm.feed('   ', now_ms=0)
        sm.feed('100', now_ms=500)   # stores candidate 100
        assert not math.isnan(sm.set_temp_potential)
        sm.feed('100', now_ms=SET_MODE_TIMEOUT_MS)  # timeout — candidate cleared
        assert math.isnan(sm.set_temp_potential)


# ---------------------------------------------------------------------------
# TestSetpointPublish
# ---------------------------------------------------------------------------

class TestSetpointPublish:
    """Blank → temp (in set mode) → blank confirms and publishes setpoint."""

    def test_blank_temp_blank_publishes_setpoint(self):
        """Classic sequence: blank → temperature → blank confirms setpoint."""
        sm = SetModeStateMachine()
        sm.feed('   ', now_ms=0)         # enter set mode
        sm.feed('100', now_ms=200)       # store candidate 100
        result = sm.feed('   ', now_ms=400)  # confirmation blank
        assert result == ('setpoint', 100.0)
        assert sm.published_setpoint == 100.0

    def test_published_value_equals_candidate_temp(self):
        """Confirmed setpoint equals the last stored candidate."""
        sm = SetModeStateMachine()
        sm.feed('   ', now_ms=0)
        sm.feed('104', now_ms=200)
        sm.feed('   ', now_ms=400)
        assert sm.detected_setpoint == 104.0
        assert sm.published_setpoint == 104.0

    def test_same_value_not_republished(self):
        """Same setpoint value is not republished if it hasn't changed."""
        sm = SetModeStateMachine()
        # First sequence — detect setpoint 100
        sm.feed('   ', now_ms=0)
        sm.feed('100', now_ms=200)
        result1 = sm.feed('   ', now_ms=400)
        assert result1 == ('setpoint', 100.0)

        # Second sequence — same value 100 again
        sm.feed('100', now_ms=600)  # store candidate 100 again
        result2 = sm.feed('   ', now_ms=800)
        # Same value — no new setpoint publish
        assert result2 == ('blank', None)
        # published_setpoint still equals the first publish
        assert sm.published_setpoint == 100.0

    def test_different_value_is_republished(self):
        """Different setpoint value triggers a new publish."""
        sm = SetModeStateMachine()
        sm.feed('   ', now_ms=0)
        sm.feed('100', now_ms=200)
        sm.feed('   ', now_ms=400)
        assert sm.published_setpoint == 100.0

        # New sequence with different value
        sm.feed('102', now_ms=600)
        result = sm.feed('   ', now_ms=800)
        assert result == ('setpoint', 102.0)
        assert sm.published_setpoint == 102.0

    def test_candidate_cleared_after_confirmation(self):
        """After confirmation, set_temp_potential is reset to NaN."""
        sm = SetModeStateMachine()
        sm.feed('   ', now_ms=0)
        sm.feed('100', now_ms=200)
        sm.feed('   ', now_ms=400)  # confirmation
        assert math.isnan(sm.set_temp_potential)


# ---------------------------------------------------------------------------
# TestTemperatureDiscrimination
# ---------------------------------------------------------------------------

class TestTemperatureDiscrimination:
    """Normal vs suppressed temperature routing."""

    def test_normal_temperature_no_prior_blank_publishes(self):
        """Temperature with no preceding blank is published immediately."""
        sm = SetModeStateMachine()
        result = sm.feed('100', now_ms=0)
        assert result == ('temperature', 100.0)
        assert sm.published_temperature == 100.0

    def test_temperature_during_set_mode_is_suppressed(self):
        """Temperature immediately after blank (within timeout) is suppressed."""
        sm = SetModeStateMachine()
        sm.feed('   ', now_ms=0)
        result = sm.feed('100', now_ms=500)
        assert result == ('suppressed', 100.0)
        assert sm.published_temperature is None  # not published to temp sensor

    def test_temperature_after_timeout_publishes_normally(self):
        """Temperature after set-mode timeout publishes to temperature sensor."""
        sm = SetModeStateMachine()
        sm.feed('   ', now_ms=0)
        result = sm.feed('100', now_ms=SET_MODE_TIMEOUT_MS + 1)
        assert result == ('temperature', 100.0)
        assert sm.published_temperature == 100.0

    def test_multiple_suppressed_temperatures_store_last_candidate(self):
        """Multiple temperature frames in set mode store the latest as candidate."""
        sm = SetModeStateMachine()
        sm.feed('   ', now_ms=0)
        sm.feed('98', now_ms=100)
        sm.feed('100', now_ms=200)
        sm.feed('102', now_ms=300)
        # Candidate should be the last temperature seen before blank
        assert sm.set_temp_potential == 102.0


# ---------------------------------------------------------------------------
# TestButtonInjectorFeed
# ---------------------------------------------------------------------------

class TestButtonInjectorFeed:
    """When setpoint is confirmed, set_known_setpoint() is called with detected value."""

    def test_known_setpoint_fed_on_confirmation(self):
        """Confirming a setpoint sets known_setpoint_fed to the detected value."""
        sm = SetModeStateMachine()
        sm.feed('   ', now_ms=0)
        sm.feed('100', now_ms=200)
        sm.feed('   ', now_ms=400)
        assert sm.known_setpoint_fed == 100.0

    def test_known_setpoint_not_fed_before_confirmation(self):
        """known_setpoint_fed remains None until setpoint is confirmed."""
        sm = SetModeStateMachine()
        sm.feed('   ', now_ms=0)
        sm.feed('100', now_ms=200)
        # No second blank yet — not confirmed
        assert sm.known_setpoint_fed is None

    def test_known_setpoint_fed_with_correct_value(self):
        """The value fed to the injector matches the confirmed setpoint."""
        sm = SetModeStateMachine()
        sm.feed('   ', now_ms=0)
        sm.feed('104', now_ms=200)
        sm.feed('   ', now_ms=400)
        assert sm.known_setpoint_fed == 104.0
        assert sm.known_setpoint_fed == sm.detected_setpoint

    def test_known_setpoint_not_fed_on_same_value(self):
        """Same setpoint value does not re-feed the injector."""
        sm = SetModeStateMachine()
        # First detection
        sm.feed('   ', now_ms=0)
        sm.feed('100', now_ms=200)
        sm.feed('   ', now_ms=400)
        assert sm.known_setpoint_fed == 100.0

        # Reset to detect whether feed happens again
        sm.known_setpoint_fed = None

        # Second sequence, same value
        sm.feed('100', now_ms=600)
        sm.feed('   ', now_ms=800)
        assert sm.known_setpoint_fed is None  # not re-fed

    def test_injector_receives_updated_setpoint(self):
        """When setpoint changes, injector receives the new value."""
        sm = SetModeStateMachine()
        sm.feed('   ', now_ms=0)
        sm.feed('100', now_ms=200)
        sm.feed('   ', now_ms=400)

        sm.feed('102', now_ms=600)
        sm.feed('   ', now_ms=800)
        assert sm.known_setpoint_fed == 102.0
