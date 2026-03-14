"""Tests for temperature ladder capture script.

Tests the pure parsing/validation functions used by the ladder capture CLI.
All tests use synthetic data -- no serial port or hardware needed.
"""

import csv
import io
from pathlib import Path

import pytest

from ladder_capture import (
    build_ladder_entry,
    extract_stable_frames,
    generate_lookup_update,
    parse_capture_line,
    validate_ladder,
    write_ladder_csv,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_capture_lines():
    """Realistic capture lines in the format produced by rs485_capture.py."""
    return [
        "[   1.234] (  8 bytes) FE 06 70 E6 00 06 70 00",
        "[   2.456] (  8 bytes) FE 06 70 E6 00 06 70 00",
        "[   3.789] (  8 bytes) FE 06 70 E6 00 06 70 00",
        "[   4.012] (  8 bytes) FE 06 70 E6 00 06 70 00",
        "[   5.345] (  8 bytes) FE 06 30 7E 33 06 70 00",
        "[   6.678] (  8 bytes) FE 06 30 7E 33 06 70 00",
    ]


@pytest.fixture
def stable_104_frames():
    """Three consecutive identical frames representing 104F stable reading."""
    return [
        bytes([0xFE, 0x06, 0x30, 0x7E, 0x33, 0x06, 0x70, 0x00]),
        bytes([0xFE, 0x06, 0x30, 0x7E, 0x33, 0x06, 0x70, 0x00]),
        bytes([0xFE, 0x06, 0x30, 0x7E, 0x33, 0x06, 0x70, 0x00]),
    ]


@pytest.fixture
def complete_ladder():
    """A valid ladder with entries at 6 distinct temperatures."""
    temperatures = [104, 103, 102, 101, 100, 99]
    # Create distinct byte_3 values for each temperature
    byte3_values = [0x33, 0x79, 0x6D, 0x30, 0x7E, 0x7B]
    entries = []
    for temp, b3 in zip(temperatures, byte3_values):
        frame = bytes([0xFE, 0x06, 0x30, b3, 0x00, 0x06, 0x70, 0x00])
        entries.append(
            build_ladder_entry(
                temperature=temp,
                stable_frames=[frame, frame, frame],
                timestamp=1.0,
            )
        )
    return entries


@pytest.fixture
def incomplete_ladder():
    """A ladder with only 3 temperatures -- should fail validation."""
    entries = []
    for temp in [104, 103, 102]:
        frame = bytes([0xFE, 0x06, 0x30, 0x33, 0x00, 0x06, 0x70, 0x00])
        entries.append(
            build_ladder_entry(
                temperature=temp,
                stable_frames=[frame, frame, frame],
                timestamp=1.0,
            )
        )
    return entries


# ---------------------------------------------------------------------------
# Test 1: parse_capture_line
# ---------------------------------------------------------------------------


class TestParseCaptureLinee:
    def test_parses_timestamp(self, sample_capture_lines):
        result = parse_capture_line(sample_capture_lines[0])
        assert result["timestamp"] == pytest.approx(1.234)

    def test_parses_byte_count(self, sample_capture_lines):
        result = parse_capture_line(sample_capture_lines[0])
        assert result["byte_count"] == 8

    def test_parses_hex_bytes(self, sample_capture_lines):
        result = parse_capture_line(sample_capture_lines[0])
        assert result["raw_bytes"] == bytes(
            [0xFE, 0x06, 0x70, 0xE6, 0x00, 0x06, 0x70, 0x00]
        )

    def test_returns_none_for_invalid_line(self):
        result = parse_capture_line("===== MARKER 1: [temp down] at 5.0s =====")
        assert result is None

    def test_returns_none_for_empty_line(self):
        result = parse_capture_line("")
        assert result is None


# ---------------------------------------------------------------------------
# Test 2: extract_stable_frames
# ---------------------------------------------------------------------------


class TestExtractStableFrames:
    def test_finds_stable_sequence(self):
        """Three consecutive identical frames should be detected as stable."""
        frame_a = bytes([0xFE, 0x06, 0x70, 0xE6, 0x00, 0x06, 0x70, 0x00])
        frame_b = bytes([0xFE, 0x06, 0x30, 0x7E, 0x33, 0x06, 0x70, 0x00])
        parsed = [
            {"timestamp": 1.0, "byte_count": 8, "raw_bytes": frame_a},
            {"timestamp": 2.0, "byte_count": 8, "raw_bytes": frame_a},
            {"timestamp": 3.0, "byte_count": 8, "raw_bytes": frame_a},
            {"timestamp": 4.0, "byte_count": 8, "raw_bytes": frame_b},
        ]
        stable = extract_stable_frames(parsed)
        assert len(stable) >= 1
        assert stable[0]["frame"] == frame_a
        assert stable[0]["count"] >= 3

    def test_no_stable_if_all_different(self):
        """No stable frames if every frame is different."""
        parsed = [
            {"timestamp": float(i), "byte_count": 8, "raw_bytes": bytes([i] * 8)}
            for i in range(10)
        ]
        stable = extract_stable_frames(parsed)
        assert len(stable) == 0

    def test_multiple_stable_groups(self):
        """Finds multiple distinct stable groups."""
        frame_a = bytes([0xFE] * 8)
        frame_b = bytes([0x00] * 8)
        parsed = [
            {"timestamp": 1.0, "byte_count": 8, "raw_bytes": frame_a},
            {"timestamp": 2.0, "byte_count": 8, "raw_bytes": frame_a},
            {"timestamp": 3.0, "byte_count": 8, "raw_bytes": frame_a},
            {"timestamp": 4.0, "byte_count": 8, "raw_bytes": frame_b},
            {"timestamp": 5.0, "byte_count": 8, "raw_bytes": frame_b},
            {"timestamp": 6.0, "byte_count": 8, "raw_bytes": frame_b},
        ]
        stable = extract_stable_frames(parsed)
        assert len(stable) == 2


# ---------------------------------------------------------------------------
# Test 3: build_ladder_entry
# ---------------------------------------------------------------------------


class TestBuildLadderEntry:
    def test_creates_structured_dict(self, stable_104_frames):
        entry = build_ladder_entry(
            temperature=104, stable_frames=stable_104_frames, timestamp=1.234
        )
        assert entry["temperature"] == 104
        assert entry["stable_frames"] == stable_104_frames
        assert entry["byte_3_value"] == 0x33
        assert isinstance(entry["raw_hex"], str)

    def test_raw_hex_format(self, stable_104_frames):
        entry = build_ladder_entry(
            temperature=104, stable_frames=stable_104_frames, timestamp=1.234
        )
        # raw_hex should be space-separated hex of the first stable frame
        assert entry["raw_hex"] == "FE 06 30 7E 33 06 70 00"

    def test_byte_3_extracted(self):
        frame = bytes([0xFE, 0x06, 0x30, 0x5B, 0x00, 0x06, 0x70, 0x00])
        entry = build_ladder_entry(
            temperature=95, stable_frames=[frame, frame, frame], timestamp=2.0
        )
        assert entry["byte_3_value"] == 0x5B


# ---------------------------------------------------------------------------
# Test 4: validate_ladder
# ---------------------------------------------------------------------------


class TestValidateLadder:
    def test_valid_ladder_passes(self, complete_ladder):
        is_valid, errors = validate_ladder(complete_ladder)
        assert is_valid is True
        assert len(errors) == 0

    def test_rejects_too_few_temperatures(self, incomplete_ladder):
        is_valid, errors = validate_ladder(incomplete_ladder)
        assert is_valid is False
        assert any("5" in e or "temperature" in e.lower() for e in errors)

    def test_rejects_empty_ladder(self):
        is_valid, errors = validate_ladder([])
        assert is_valid is False


# ---------------------------------------------------------------------------
# Test 5: generate_lookup_update
# ---------------------------------------------------------------------------


class TestGenerateLookupUpdate:
    def test_maps_byte_values_to_digits(self, complete_ladder):
        # complete_ladder has temperatures 104, 103, 102, 101, 100, 99
        # byte_3 values: 0x33, 0x79, 0x6D, 0x30, 0x7E, 0x7B
        # For ones digit: 104->4 (byte_3=0x33), 103->3 (byte_3=0x79), etc.
        lookup = generate_lookup_update(complete_ladder)
        assert isinstance(lookup, dict)
        # Should have mappings for the byte values seen
        assert 0x33 in lookup  # ones digit of 104 = "4"
        assert lookup[0x33] == "4"
        assert 0x79 in lookup  # ones digit of 103 = "3"
        assert lookup[0x79] == "3"

    def test_cross_references_seven_seg_table(self, complete_ladder):
        """Lookup should contain entries that can be compared to SEVEN_SEG_TABLE."""
        lookup = generate_lookup_update(complete_ladder)
        # All values should be single digit characters
        for byte_val, char in lookup.items():
            assert isinstance(byte_val, int)
            assert isinstance(char, str)
            assert len(char) == 1


# ---------------------------------------------------------------------------
# Test 6: write_ladder_csv
# ---------------------------------------------------------------------------


class TestWriteLadderCsv:
    def test_writes_csv_format(self, complete_ladder):
        buf = io.StringIO()
        write_ladder_csv(complete_ladder, buf)
        buf.seek(0)
        reader = csv.DictReader(buf)
        rows = list(reader)
        assert len(rows) == len(complete_ladder)

    def test_csv_has_required_columns(self, complete_ladder):
        buf = io.StringIO()
        write_ladder_csv(complete_ladder, buf)
        buf.seek(0)
        reader = csv.DictReader(buf)
        fieldnames = reader.fieldnames
        expected = [
            "temperature",
            "byte_0",
            "byte_1",
            "byte_2",
            "byte_3",
            "byte_4",
            "byte_5",
            "byte_6",
            "byte_7",
            "stable_frame_count",
            "timestamp",
        ]
        for col in expected:
            assert col in fieldnames, f"Missing CSV column: {col}"

    def test_csv_temperature_values(self, complete_ladder):
        buf = io.StringIO()
        write_ladder_csv(complete_ladder, buf)
        buf.seek(0)
        reader = csv.DictReader(buf)
        temps = [int(row["temperature"]) for row in reader]
        assert temps == [entry["temperature"] for entry in complete_ladder]
