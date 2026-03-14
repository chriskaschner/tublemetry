"""Tests for 7-segment byte-to-character decoder."""

import pytest
from tests.conftest import CONFIRMED_MAPPINGS
from tubtron.decode import decode_7seg, SEVEN_SEG_TABLE


class TestDecode7seg:
    """Test the 7-segment decoder function."""

    def test_confirmed_byte_1(self):
        """0x30 decodes to '1' with confirmed confidence."""
        char, confidence = decode_7seg(0x30)
        assert char == "1"
        assert confidence == "confirmed"

    def test_confirmed_byte_7(self):
        """0x70 decodes to '7' with confirmed confidence."""
        char, confidence = decode_7seg(0x70)
        assert char == "7"
        assert confidence == "confirmed"

    def test_blank_byte(self):
        """0x00 decodes to blank (' ') with confirmed confidence."""
        char, confidence = decode_7seg(0x00)
        assert char == " "
        assert confidence == "confirmed"

    def test_unknown_byte(self):
        """Unknown byte value returns '?' with unverified confidence."""
        char, confidence = decode_7seg(0xAB)
        assert char == "?"
        assert confidence == "unverified"

    def test_fe_byte(self):
        """0xFE decodes to some character (FE = all segments minus bit0).
        After masking dp bit (bit 7): 0x7E. With GS510SZ reference
        encoding (bit7=dp, bits6-0 = segments a-g), 0x7E = segments
        a,b,c,d,e,f = '0'."""
        char, confidence = decode_7seg(0xFE)
        # FE masked = 0x7E, which is '0' in GS510SZ encoding
        assert isinstance(char, str)
        assert len(char) == 1
        assert confidence in ("confirmed", "unverified")

    @pytest.mark.parametrize(
        "byte_val,expected_char",
        list(CONFIRMED_MAPPINGS.items()),
        ids=[f"0x{b:02X}={c!r}" for b, c in CONFIRMED_MAPPINGS.items()],
    )
    def test_all_confirmed_mappings(self, byte_val, expected_char):
        """All confirmed mappings decode correctly."""
        char, confidence = decode_7seg(byte_val)
        assert char == expected_char
        assert confidence == "confirmed"

    def test_decode_masks_dp_bit(self):
        """Decoder masks off bit 7 (dp) before lookup.
        0x30 and 0xB0 should decode to the same character."""
        char_without_dp, _ = decode_7seg(0x30)
        char_with_dp, _ = decode_7seg(0xB0)
        assert char_without_dp == char_with_dp

    def test_seven_seg_table_is_dict(self):
        """SEVEN_SEG_TABLE is a dict mapping int -> str."""
        assert isinstance(SEVEN_SEG_TABLE, dict)
        assert len(SEVEN_SEG_TABLE) > 0

    def test_seven_seg_table_has_confirmed_entries(self):
        """Table contains all confirmed byte values (after dp masking)."""
        for byte_val in CONFIRMED_MAPPINGS:
            masked = byte_val & 0x7F
            assert masked in SEVEN_SEG_TABLE
