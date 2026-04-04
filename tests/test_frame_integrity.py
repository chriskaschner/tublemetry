"""Frame integrity tests — checksum gate and stability filter.

These tests mirror the C++ logic in tublemetry_display.cpp:
  - passes_checksum(): mirrors the checksum gate (CHECKSUM_MASK=0x4B on p1, bit0 on p4)
  - StabilityFilter: mirrors the STABLE_THRESHOLD=3 consecutive-match requirement

Frame layout: [digit1:7][digit2:7][digit3:7][status:3] = 24 bits MSB-first
p1 = digit1 = bits 23-17
p4 = status = bits 2-0
"""

import pytest

from tests.test_mock_frames import digits_to_frame, frame_to_digits, frame_to_display_string


# ---------------------------------------------------------------------------
# Python mirrors of C++ constants and logic
# ---------------------------------------------------------------------------

CHECKSUM_MASK = 0x4B   # bits 6,3,1,0 must be zero in p1
STABLE_THRESHOLD = 3


def passes_checksum(frame_bits: int) -> bool:
    """Mirror of the C++ checksum gate in process_frame_().

    Returns True if p1 bits 6,3,1,0 are all zero AND p4 bit 0 is zero.
    """
    p1 = (frame_bits >> 17) & 0x7F   # digit1 — bits 23-17
    p4 = frame_bits & 0x07            # status — bits 2-0
    return (p1 & CHECKSUM_MASK) == 0x00 and (p4 & 0x01) == 0x00


class StabilityFilter:
    """Mirror of the C++ stability filter in process_frame_().

    Requires STABLE_THRESHOLD consecutive identical display strings before
    returning True (should publish).  Saturation: count caps at 255.
    """

    def __init__(self) -> None:
        self.candidate: str | None = None
        self.count: int = 0

    def feed(self, display_str: str) -> bool:
        """Feed one decoded display string.  Returns True when stable enough to publish."""
        if display_str == self.candidate:
            if self.count < 255:
                self.count += 1
        else:
            self.candidate = display_str
            self.count = 1
        return self.count >= STABLE_THRESHOLD


# ---------------------------------------------------------------------------
# Checksum tests
# ---------------------------------------------------------------------------

class TestChecksumValid:
    """Frames that should pass the checksum gate."""

    def test_checksum_valid_blank(self):
        """Blank hundreds digit (p1=0x00) + valid tens/ones — should pass."""
        frame = digits_to_frame(0x00, 0x7E, 0x79, 0)   # " 03"
        assert passes_checksum(frame) is True

    def test_checksum_valid_1_as_hundreds(self):
        """p1='1' (0x30 = 0b00110000) — bits 6,3,1,0 all clear."""
        frame = digits_to_frame(0x30, 0x7E, 0x5B, 0)   # "105"
        assert passes_checksum(frame) is True

    def test_checksum_valid_1_variant(self):
        """p1='1' alternate encoding (0x34 = 0b00110100) — bits 6,3,1,0 all clear."""
        frame = digits_to_frame(0x34, 0x7E, 0x5B, 0)   # "105" alt
        assert passes_checksum(frame) is True

    def test_checksum_allows_p4_bit1_bit2(self):
        """p4 with bits 1 and 2 set (value=6) is still valid — only bit 0 is checked."""
        frame = digits_to_frame(0x00, 0x7E, 0x79, 6)   # status=0b110
        assert passes_checksum(frame) is True


class TestChecksumRejects:
    """Frames that should be rejected by the checksum gate."""

    def test_checksum_rejects_zero_display(self):
        """p1=0x7E ('0') — bit 6 set in mask, must fail."""
        # 0x7E = 0b01111110; 0x7E & 0x4B = 0x4A != 0
        frame = digits_to_frame(0x7E, 0x7E, 0x7E, 0)   # "000"
        assert passes_checksum(frame) is False

    def test_checksum_rejects_startup_dash(self):
        """p1=0x01 ('-' dash glyph) — bit 0 set in mask, must fail."""
        # 0x01 = 0b00000001; 0x01 & 0x4B = 0x01 != 0
        frame = digits_to_frame(0x01, 0x01, 0x01, 0)   # "---"
        assert passes_checksum(frame) is False

    def test_checksum_rejects_p4_bit0(self):
        """p4 bit 0 set — must fail regardless of p1."""
        frame = digits_to_frame(0x00, 0x7E, 0x79, 1)   # status=0b001
        assert passes_checksum(frame) is False

    def test_checksum_rejects_p4_bit0_with_valid_p1(self):
        """p1 valid but p4 bit 0 set — still fails."""
        frame = digits_to_frame(0x30, 0x7E, 0x5B, 1)   # "105" but status=1
        assert passes_checksum(frame) is False

    def test_checksum_rejects_p1_bit3(self):
        """p1 with bit 3 set (0x08 = 0b00001000) — fails on bit 3 in mask."""
        frame = digits_to_frame(0x08, 0x7E, 0x79, 0)
        assert passes_checksum(frame) is False

    def test_checksum_rejects_p1_bit1(self):
        """p1 with bit 1 set (0x02 = 0b00000010) — fails on bit 1 in mask."""
        frame = digits_to_frame(0x02, 0x7E, 0x79, 0)
        assert passes_checksum(frame) is False


class TestChecksumRealFrames:
    """Known real captured frames verified against checksum gate."""

    def test_105f_passes(self):
        """FRAME_105F from test_mock_frames passes checksum."""
        frame = digits_to_frame(0x30, 0x7E, 0x5B, 0)
        assert passes_checksum(frame) is True

    def test_104f_passes(self):
        """FRAME_104F passes checksum."""
        frame = digits_to_frame(0x30, 0x7E, 0x33, 0)
        assert passes_checksum(frame) is True

    def test_80f_passes(self):
        """' 80' frame passes checksum (p1=0x00)."""
        frame = digits_to_frame(0x00, 0x7F, 0x7E, 0)
        assert passes_checksum(frame) is True

    def test_ec_mode_passes(self):
        """Economy mode frame passes checksum (p1=0x00)."""
        frame = digits_to_frame(0x00, 0x4F, 0x0D, 4)
        assert passes_checksum(frame) is True

    def test_blank_passes(self):
        """All-zero frame passes checksum (p1=0x00, p4=0)."""
        frame = digits_to_frame(0x00, 0x00, 0x00, 0)
        assert passes_checksum(frame) is True


# ---------------------------------------------------------------------------
# Stability filter tests
# ---------------------------------------------------------------------------

class TestStabilityFilter:
    """Stability filter: 3 consecutive identical strings required before publish."""

    def test_stability_two_frames_hold(self):
        """Two identical frames must not publish — need one more."""
        sf = StabilityFilter()
        assert sf.feed("105") is False
        assert sf.feed("105") is False

    def test_stability_three_frames_publish(self):
        """Three consecutive identical frames trigger publish on the third."""
        sf = StabilityFilter()
        assert sf.feed("105") is False
        assert sf.feed("105") is False
        assert sf.feed("105") is True

    def test_stability_reset_on_change(self):
        """Streak resets when display string changes."""
        sf = StabilityFilter()
        assert sf.feed("105") is False
        assert sf.feed("105") is False
        # Change — streak resets, new candidate starts at count=1
        assert sf.feed("104") is False

    def test_stability_new_streak_after_reset(self):
        """New streak of 3 publishes after an earlier streak was broken."""
        sf = StabilityFilter()
        sf.feed("105")
        sf.feed("105")
        # Break streak
        sf.feed("104")    # count=1 for "104", no publish
        sf.feed("104")    # count=2
        assert sf.feed("104") is True   # count=3 → publish

    def test_stability_fourth_frame_still_publishes(self):
        """Frames after the threshold is reached continue to return True."""
        sf = StabilityFilter()
        sf.feed("105"); sf.feed("105"); sf.feed("105")  # reaches threshold
        assert sf.feed("105") is True   # 4th identical — still True

    def test_stability_single_frame_never_publishes(self):
        """A single frame of any value never publishes."""
        sf = StabilityFilter()
        assert sf.feed(" 80") is False

    def test_stability_saturation(self):
        """count saturates at 255 — does not overflow uint8-equivalent range."""
        sf = StabilityFilter()
        for _ in range(300):
            sf.feed("105")
        # count capped at 255, still >= STABLE_THRESHOLD
        assert sf.count == 255
        assert sf.feed("105") is True

    def test_stability_independent_instances(self):
        """Two StabilityFilter instances track state independently."""
        sf1 = StabilityFilter()
        sf2 = StabilityFilter()
        sf1.feed("105"); sf1.feed("105"); sf1.feed("105")
        sf2.feed("104")
        assert sf1.feed("105") is True   # sf1 well past threshold
        assert sf2.feed("104") is False  # sf2 only at count=2

    def test_stability_different_strings_never_accumulate(self):
        """Alternating strings never accumulate a streak."""
        sf = StabilityFilter()
        for _ in range(10):
            assert sf.feed("105") is False
            assert sf.feed("104") is False

    def test_stability_blank_and_temp(self):
        """Realistic pattern: three blanks then three temperatures."""
        sf = StabilityFilter()
        # Three blanks
        sf.feed("   "); sf.feed("   ")
        assert sf.feed("   ") is True   # blank streak reaches threshold
        # Temperature change — resets
        sf.feed("105"); sf.feed("105")
        assert sf.feed("105") is True   # temp streak reaches threshold
