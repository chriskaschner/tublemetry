"""Tests for Pin 5 RS-485 frame parser."""

import pytest
from tests.conftest import IDLE_FRAME_A, IDLE_FRAME_B, TEMP_DOWN_FRAME
from tublemetry.frame_parser import parse_pin5_frame, FrameResult


class TestFrameParser:
    """Test the Pin 5 frame parser."""

    def test_idle_frame_a_returns_frame_result(self):
        """parse_pin5_frame returns a FrameResult dataclass."""
        result = parse_pin5_frame(IDLE_FRAME_A)
        assert isinstance(result, FrameResult)

    def test_idle_frame_a_has_display_string(self):
        """FrameResult contains a display_string field."""
        result = parse_pin5_frame(IDLE_FRAME_A)
        assert isinstance(result.display_string, str)
        assert len(result.display_string) > 0

    def test_idle_frame_b_different_display(self):
        """IDLE_FRAME_B produces a different display_string than IDLE_FRAME_A
        (byte 3 differs: 0x30 vs 0xE6)."""
        result_a = parse_pin5_frame(IDLE_FRAME_A)
        result_b = parse_pin5_frame(IDLE_FRAME_B)
        assert result_a.display_string != result_b.display_string

    def test_frame_has_fe_marker(self):
        """IDLE_FRAME_A starts with 0xFE, so has_fe_marker should be True."""
        result = parse_pin5_frame(IDLE_FRAME_A)
        assert result.has_fe_marker is True

    def test_frame_without_fe_marker(self):
        """TEMP_DOWN_FRAME starts with 0x06, so has_fe_marker should be False."""
        result = parse_pin5_frame(TEMP_DOWN_FRAME)
        assert result.has_fe_marker is False

    def test_rejects_short_frame(self):
        """Frames shorter than 8 bytes are rejected with ValueError."""
        with pytest.raises(ValueError, match="8 bytes"):
            parse_pin5_frame(bytes(4))

    def test_rejects_long_frame(self):
        """Frames longer than 8 bytes are rejected with ValueError."""
        with pytest.raises(ValueError, match="8 bytes"):
            parse_pin5_frame(bytes(12))

    def test_raw_hex_field(self):
        """raw_hex contains space-separated uppercase hex string."""
        result = parse_pin5_frame(IDLE_FRAME_A)
        assert result.raw_hex == "FE 06 70 30 00 06 70 00"

    def test_digit_values_length(self):
        """digit_values contains one entry per byte in the frame."""
        result = parse_pin5_frame(IDLE_FRAME_A)
        assert len(result.digit_values) == 8

    def test_digit_values_are_tuples(self):
        """Each entry in digit_values is a (char, confidence) tuple."""
        result = parse_pin5_frame(IDLE_FRAME_A)
        for item in result.digit_values:
            assert isinstance(item, tuple)
            assert len(item) == 2
            char, confidence = item
            assert isinstance(char, str)
            assert confidence in ("confirmed", "unverified")

    def test_sub_frames(self):
        """FrameResult splits frame into sub_frame_1 (bytes 0-3) and
        sub_frame_2 (bytes 4-7)."""
        result = parse_pin5_frame(IDLE_FRAME_A)
        assert result.sub_frame_1 == bytes([0xFE, 0x06, 0x70, 0x30])
        assert result.sub_frame_2 == bytes([0x00, 0x06, 0x70, 0x00])

    def test_temp_down_frame_raw_hex(self):
        """Verify raw_hex for temp-down frame."""
        result = parse_pin5_frame(TEMP_DOWN_FRAME)
        assert result.raw_hex == "06 70 E6 00 00 06 00 F3"
