"""Tests for display state machine (temperature persistence, edge states)."""

import pytest
from tublemetry.display_state import DisplayState, update_display


class TestDisplayState:
    """Test the display state machine."""

    def test_initial_state_has_no_temperature(self):
        """Fresh DisplayState has temperature == None."""
        state = DisplayState()
        assert state.temperature is None

    def test_initial_display_state(self):
        """Fresh DisplayState has display_state == 'unknown'."""
        state = DisplayState()
        assert state.display_state == "unknown"

    def test_valid_temperature_three_digit(self):
        """update_display('104') sets temperature to 104."""
        state = DisplayState()
        state = update_display(state, "104")
        assert state.temperature == 104.0
        assert state.display_state == "temperature"

    def test_valid_temperature_two_digit(self):
        """update_display('99') sets temperature to 99."""
        state = DisplayState()
        state = update_display(state, "99")
        assert state.temperature == 99.0
        assert state.display_state == "temperature"

    def test_oh_keeps_temperature(self):
        """OH display keeps last valid temperature."""
        state = DisplayState()
        state = update_display(state, "104")
        assert state.temperature == 104.0
        state = update_display(state, "OH")
        assert state.temperature == 104.0
        assert state.display_state == "OH"

    def test_ice_keeps_temperature(self):
        """ICE display keeps last valid temperature."""
        state = DisplayState()
        state = update_display(state, "100")
        assert state.temperature == 100.0
        state = update_display(state, "ICE")
        assert state.temperature == 100.0
        assert state.display_state == "ICE"

    def test_startup_dashes(self):
        """Startup dashes ('--') set display_state to 'startup'."""
        state = DisplayState()
        state = update_display(state, "--")
        assert state.display_state == "startup"
        assert state.temperature is None  # No valid reading yet

    def test_startup_dashes_keep_temperature(self):
        """Startup dashes after a valid reading keep last temperature."""
        state = DisplayState()
        state = update_display(state, "102")
        state = update_display(state, "--")
        assert state.temperature == 102.0
        assert state.display_state == "startup"

    def test_temp_out_of_range_low_confidence(self):
        """Temperature outside 80-120 range is flagged as low confidence."""
        state = DisplayState()
        state = update_display(state, "150")
        assert state.temperature == 150.0
        assert state.confidence == "low"

    def test_temp_in_range_normal_confidence(self):
        """Temperature within 80-120 range has normal confidence."""
        state = DisplayState()
        state = update_display(state, "104")
        assert state.confidence == "normal"

    def test_setpoint_flash_reported_faithfully(self):
        """Dumb decoder: setpoint flash updates temperature value.
        When display shows '103' after temperature was '104',
        the decoder reports 103 faithfully (no interpretation)."""
        state = DisplayState()
        state = update_display(state, "104")
        assert state.temperature == 104.0
        state = update_display(state, "103")
        assert state.temperature == 103.0

    def test_display_string_preserved(self):
        """The raw display_string is preserved in the state."""
        state = DisplayState()
        state = update_display(state, "104")
        assert state.display_string == "104"

    def test_oh_display_string(self):
        """OH display string is preserved."""
        state = DisplayState()
        state = update_display(state, "OH")
        assert state.display_string == "OH"
        assert state.display_state == "OH"

    def test_multiple_transitions(self):
        """State machine handles multiple transitions correctly."""
        state = DisplayState()
        state = update_display(state, "104")
        assert state.temperature == 104.0
        assert state.display_state == "temperature"

        state = update_display(state, "OH")
        assert state.temperature == 104.0
        assert state.display_state == "OH"

        state = update_display(state, "103")
        assert state.temperature == 103.0
        assert state.display_state == "temperature"

        state = update_display(state, "--")
        assert state.temperature == 103.0
        assert state.display_state == "startup"

        state = update_display(state, "ICE")
        assert state.temperature == 103.0
        assert state.display_state == "ICE"

        state = update_display(state, "99")
        assert state.temperature == 99.0
        assert state.display_state == "temperature"

    def test_blank_display_string(self):
        """Blank or whitespace-only display string is classified as 'blank'."""
        state = DisplayState()
        state = update_display(state, "   ")
        assert state.display_state == "blank"

    def test_unknown_display_string(self):
        """Unrecognized non-numeric, non-known-pattern string is 'unknown'."""
        state = DisplayState()
        state = update_display(state, "???")
        assert state.display_state == "unknown"
