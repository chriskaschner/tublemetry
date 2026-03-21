"""Mock frame tests — exercise the full decode pipeline with real captured data.

Tests feed known 24-bit frame values through the decode pipeline:
  raw frame → extract 3x7-bit digits → 7-seg decode → display string
  → temperature extraction → state classification

Frame layout (from protocol analysis):
  [digit1:7][digit2:7][digit3:7][status:3] = 24 bits total, MSB-first

Test data sourced from logic analyzer captures (485/examples/) and
ladder capture results (485/captures/).
"""

import pytest

from tublemetry.decode import decode_7seg, SEVEN_SEG_TABLE
from tublemetry.display_state import DisplayState, update_display


# --- Helpers: simulate C++ frame processing in Python ---

def frame_to_digits(frame_bits: int) -> tuple[int, int, int, int]:
    """Extract 3 digit bytes and status from a 24-bit frame.

    Mirrors TublemetryDisplay::process_frame_() logic.
    """
    digit1 = (frame_bits >> 17) & 0x7F  # bits 23-17
    digit2 = (frame_bits >> 10) & 0x7F  # bits 16-10
    digit3 = (frame_bits >> 3) & 0x7F   # bits 9-3
    status = frame_bits & 0x07           # bits 2-0
    return digit1, digit2, digit3, status


def frame_to_display_string(frame_bits: int) -> str:
    """Decode a 24-bit frame to its display string."""
    d1, d2, d3, _ = frame_to_digits(frame_bits)
    chars = [decode_7seg(b)[0] for b in (d1, d2, d3)]
    return "".join(chars)


def digits_to_frame(d1: int, d2: int, d3: int, status: int = 0) -> int:
    """Build a 24-bit frame from 3 digit bytes and status bits."""
    return (d1 << 17) | (d2 << 10) | (d3 << 3) | (status & 0x07)


# --- Known frame values from captures ---

# Steady 105F: digit1=0x30("1"), digit2=0x7E("0"), digit3=0x5B("5"), status=0
FRAME_105F = 0b011000011111100101101_1000
# Recalculate properly from the README:
#   Frame bits: 011000011111100110011000
#   d1: 0110000 = 0x30 = "1"
#   d2: 1111110 = 0x7E = "0"
#   d3: 1011011 = 0x5B = "5"
#   status: 000
FRAME_105F = int("011000011111100101101_1000".replace("_", ""), 2)
# Let's just build it from known values
FRAME_105F = digits_to_frame(0x30, 0x7E, 0x5B, 0)

# Economy mode: digit1=0x00(" "), digit2=0x4F("E"), digit3=0x0D("c"), status=4
FRAME_EC = digits_to_frame(0x00, 0x4F, 0x0D, 4)

# Blank frame: all zeros
FRAME_BLANK = digits_to_frame(0x00, 0x00, 0x00, 0)

# OH display: digit1=0x7E("0")?  No -- "OH" is 2 chars with leading blank
# From captures: " OH" would be blank + O + H
# But OH.csv shows 0x37="H" confirmed. "O" isn't in our table as uppercase.
# The display likely shows "OH " or similar -- let's use what we know:
# Actually from display_state.py, "OH" is recognized. Let's test with known bytes.

# 104F: "1"=0x30, "0"=0x7E, "4"=0x33
FRAME_104F = digits_to_frame(0x30, 0x7E, 0x33, 0)

# 80F: " 80" = blank, "8"=0x7F, "0"=0x7E
FRAME_80F = digits_to_frame(0x00, 0x7F, 0x7E, 0)

# 99F: " 99" = blank, "9"=0x73, "9"=0x73
FRAME_99F = digits_to_frame(0x00, 0x73, 0x73, 0)

# SL mode: " SL" = blank, "5"=0x5B (looks like S), "L"=0x0E
# Actually from captures, SL uses 0x5B for S and 0x0E for L
FRAME_SL = digits_to_frame(0x00, 0x5B, 0x0E, 0)

# St mode: " St" = blank, "5"=0x5B (S), "t"=0x0F
FRAME_ST = digits_to_frame(0x00, 0x5B, 0x0F, 0)

# Startup dashes: "---" = 0x01, 0x01, 0x01
FRAME_DASHES = digits_to_frame(0x01, 0x01, 0x01, 0)


class TestFrameExtraction:
    """Verify 24-bit frame → 3x7-bit digit extraction."""

    def test_105f_digits(self):
        d1, d2, d3, status = frame_to_digits(FRAME_105F)
        assert d1 == 0x30
        assert d2 == 0x7E
        assert d3 == 0x5B
        assert status == 0

    def test_ec_mode_digits(self):
        d1, d2, d3, status = frame_to_digits(FRAME_EC)
        assert d1 == 0x00
        assert d2 == 0x4F
        assert d3 == 0x0D
        assert status == 4

    def test_blank_frame_digits(self):
        d1, d2, d3, status = frame_to_digits(FRAME_BLANK)
        assert d1 == 0x00
        assert d2 == 0x00
        assert d3 == 0x00
        assert status == 0

    def test_round_trip(self):
        """digits_to_frame and frame_to_digits are inverses."""
        for d1, d2, d3, s in [(0x30, 0x7E, 0x5B, 0), (0x00, 0x4F, 0x0D, 4),
                               (0x7F, 0x73, 0x33, 7)]:
            frame = digits_to_frame(d1, d2, d3, s)
            rd1, rd2, rd3, rs = frame_to_digits(frame)
            assert (rd1, rd2, rd3, rs) == (d1, d2, d3, s)


class TestFrameDecode:
    """Verify frame → display string decoding."""

    def test_105f(self):
        assert frame_to_display_string(FRAME_105F) == "105"

    def test_104f(self):
        assert frame_to_display_string(FRAME_104F) == "104"

    def test_80f(self):
        assert frame_to_display_string(FRAME_80F) == " 80"

    def test_99f(self):
        assert frame_to_display_string(FRAME_99F) == " 99"

    def test_ec_mode(self):
        assert frame_to_display_string(FRAME_EC) == " Ec"

    def test_blank(self):
        assert frame_to_display_string(FRAME_BLANK) == "   "

    def test_dashes(self):
        assert frame_to_display_string(FRAME_DASHES) == "---"

    def test_sl_mode(self):
        # SL uses "5" glyph for "S" — display shows "5L" which maps to "sleep"
        result = frame_to_display_string(FRAME_SL)
        assert result == " 5L"

    def test_st_mode(self):
        result = frame_to_display_string(FRAME_ST)
        assert result == " 5t"


class TestTemperatureLadder:
    """Verify all temperatures in the 80-104F range decode correctly."""

    # Build frames for each temperature using known digit encodings
    DIGIT_MAP = {
        "0": 0x7E, "1": 0x30, "2": 0x6D, "3": 0x79, "4": 0x33,
        "5": 0x5B, "6": 0x5F, "7": 0x70, "8": 0x7F, "9": 0x73,
        " ": 0x00,
    }

    @pytest.mark.parametrize("temp", range(80, 105))
    def test_temperature_decode(self, temp):
        """Each temperature in range decodes to correct display string."""
        temp_str = str(temp)
        if len(temp_str) == 2:
            d1, d2, d3 = " ", temp_str[0], temp_str[1]
        else:
            d1, d2, d3 = temp_str[0], temp_str[1], temp_str[2]

        frame = digits_to_frame(
            self.DIGIT_MAP[d1], self.DIGIT_MAP[d2], self.DIGIT_MAP[d3]
        )
        result = frame_to_display_string(frame)
        assert result.strip() == str(temp)


class TestDisplayStateFromFrame:
    """Verify frame → display state classification (full pipeline)."""

    def test_temperature_state(self):
        display_str = frame_to_display_string(FRAME_105F)
        state = update_display(DisplayState(), display_str)
        assert state.display_state == "temperature"
        assert state.temperature == 105.0
        assert state.confidence == "normal"

    def test_ec_mode_state(self):
        display_str = frame_to_display_string(FRAME_EC)
        state = update_display(DisplayState(), display_str)
        # "Ec" is not a known state in display_state.py — it's "unknown"
        # because the stripped string is "Ec", not in _KNOWN_STATES
        assert state.display_state == "unknown"

    def test_blank_state(self):
        display_str = frame_to_display_string(FRAME_BLANK)
        state = update_display(DisplayState(), display_str)
        assert state.display_state == "blank"

    def test_startup_dashes_state(self):
        display_str = frame_to_display_string(FRAME_DASHES)
        state = update_display(DisplayState(), display_str)
        assert state.display_state == "startup"

    def test_temperature_persists_through_blank(self):
        """Temperature survives non-temperature display states."""
        s1 = update_display(DisplayState(), "104")
        assert s1.temperature == 104.0

        s2 = update_display(s1, "   ")
        assert s2.display_state == "blank"
        assert s2.temperature == 104.0  # preserved

        s3 = update_display(s2, " 95")
        assert s3.temperature == 95.0  # updated to new temp

    def test_setpoint_flash_sequence(self):
        """Simulate the setpoint flash pattern: temp → blank → setpoint → blank → temp."""
        state = DisplayState()

        # Actual water temperature
        state = update_display(state, "104")
        assert state.temperature == 104.0
        assert state.display_state == "temperature"

        # Flash blank
        state = update_display(state, "   ")
        assert state.display_state == "blank"
        assert state.temperature == 104.0

        # Setpoint flash at 95F
        state = update_display(state, " 95")
        assert state.temperature == 95.0
        assert state.display_state == "temperature"

        # Flash blank again
        state = update_display(state, "   ")
        assert state.temperature == 95.0

        # Back to actual temp
        state = update_display(state, "104")
        assert state.temperature == 104.0

    def test_low_confidence_out_of_range(self):
        """Temperature outside 80-120F gets low confidence."""
        state = update_display(DisplayState(), "125")
        assert state.temperature == 125.0
        assert state.confidence == "low"

    def test_boundary_temperatures(self):
        """80F and 104F are valid normal-confidence temperatures."""
        s80 = update_display(DisplayState(), " 80")
        assert s80.temperature == 80.0
        assert s80.confidence == "normal"

        s104 = update_display(DisplayState(), "104")
        assert s104.temperature == 104.0
        assert s104.confidence == "normal"


class TestDecodeConfidence:
    """Verify decode confidence calculation matches C++ logic."""

    def test_all_known_digits(self):
        """3 known digits = 100% confidence."""
        d1, d2, d3, _ = frame_to_digits(FRAME_105F)
        known = sum(1 for b in (d1, d2, d3) if (b & 0x7F) in SEVEN_SEG_TABLE)
        assert known == 3
        assert (known / 3) * 100 == 100.0

    def test_one_unknown_digit(self):
        """1 unknown out of 3 = 66.7% confidence."""
        frame = digits_to_frame(0x30, 0x7E, 0x42, 0)  # 0x42 is unknown
        d1, d2, d3, _ = frame_to_digits(frame)
        known = sum(1 for b in (d1, d2, d3) if (b & 0x7F) in SEVEN_SEG_TABLE)
        assert known == 2
        assert round((known / 3) * 100, 1) == 66.7

    def test_all_unknown(self):
        """All unknown = 0% confidence."""
        frame = digits_to_frame(0x42, 0x43, 0x44, 0)
        d1, d2, d3, _ = frame_to_digits(frame)
        known = sum(1 for b in (d1, d2, d3) if (b & 0x7F) in SEVEN_SEG_TABLE)
        assert known == 0
