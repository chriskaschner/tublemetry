"""Cross-check test: verify C++ SEVEN_SEG_TABLE matches Python reference.

Parses the C++ source file to extract byte-to-character mappings and
compares them against the Python SEVEN_SEG_TABLE. This bridges the gap
between Python unit tests and hardware integration -- the C++ decode
logic is verified to match the Python reference without needing to
compile or run the C++ code.
"""

import re
from pathlib import Path

from tublemetry.decode import SEVEN_SEG_TABLE

# Path to the C++ implementation file
CPP_FILE = (
    Path(__file__).parent.parent
    / "esphome"
    / "components"
    / "tublemetry_display"
    / "tublemetry_display.cpp"
)


def parse_cpp_table() -> dict[int, str]:
    """Parse the C++ SEVEN_SEG_TABLE from tublemetry_display.cpp.

    Extracts entries between SEVEN_SEG_TABLE_START and SEVEN_SEG_TABLE_END
    markers. Each entry is expected in the format:
        {0xNN, 'C'},  // comment
    """
    content = CPP_FILE.read_text()

    # Find the table section between markers
    start_marker = "// SEVEN_SEG_TABLE_START"
    end_marker = "// SEVEN_SEG_TABLE_END"
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)

    assert start_idx != -1, f"Could not find {start_marker} in {CPP_FILE}"
    assert end_idx != -1, f"Could not find {end_marker} in {CPP_FILE}"

    table_section = content[start_idx:end_idx]

    # Parse entries: {0xNN, 'C'}
    pattern = re.compile(r"\{(0x[0-9A-Fa-f]+),\s*'(.)'\}")
    entries: dict[int, str] = {}

    for match in pattern.finditer(table_section):
        hex_val = int(match.group(1), 16)
        char_val = match.group(2)
        entries[hex_val] = char_val

    return entries


class TestCppPythonCrossCheck:
    """Verify C++ 7-segment lookup table matches Python reference."""

    def test_cpp_file_exists(self):
        """C++ implementation file must exist."""
        assert CPP_FILE.exists(), f"C++ file not found: {CPP_FILE}"

    def test_cpp_table_not_empty(self):
        """C++ table must have entries."""
        cpp_table = parse_cpp_table()
        assert len(cpp_table) > 0, "C++ SEVEN_SEG_TABLE is empty"

    def test_cpp_table_has_all_python_entries(self):
        """Every Python SEVEN_SEG_TABLE entry must exist in C++ table."""
        cpp_table = parse_cpp_table()

        for byte_val, expected_char in SEVEN_SEG_TABLE.items():
            assert byte_val in cpp_table, (
                f"Python entry 0x{byte_val:02X} -> '{expected_char}' "
                f"missing from C++ table"
            )
            assert cpp_table[byte_val] == expected_char, (
                f"Mismatch at 0x{byte_val:02X}: "
                f"Python='{expected_char}', C++='{cpp_table[byte_val]}'"
            )

    def test_cpp_table_has_no_contradictions(self):
        """No C++ entry should contradict the Python table."""
        cpp_table = parse_cpp_table()

        for byte_val, cpp_char in cpp_table.items():
            if byte_val in SEVEN_SEG_TABLE:
                py_char = SEVEN_SEG_TABLE[byte_val]
                assert cpp_char == py_char, (
                    f"Contradiction at 0x{byte_val:02X}: "
                    f"C++='{cpp_char}', Python='{py_char}'"
                )

    def test_confirmed_mappings_present(self):
        """Confirmed mappings (0x30='1', 0x70='7', 0x00=' ') must be in C++."""
        cpp_table = parse_cpp_table()

        confirmed = {0x30: "1", 0x70: "7", 0x00: " "}
        for byte_val, expected_char in confirmed.items():
            assert byte_val in cpp_table, (
                f"Confirmed mapping 0x{byte_val:02X} -> '{expected_char}' "
                f"missing from C++ table"
            )
            assert cpp_table[byte_val] == expected_char, (
                f"Confirmed mapping mismatch at 0x{byte_val:02X}: "
                f"expected '{expected_char}', got '{cpp_table[byte_val]}'"
            )

    def test_table_sizes_match(self):
        """C++ and Python tables should have the same number of entries."""
        cpp_table = parse_cpp_table()
        assert len(cpp_table) == len(SEVEN_SEG_TABLE), (
            f"Table size mismatch: C++ has {len(cpp_table)} entries, "
            f"Python has {len(SEVEN_SEG_TABLE)} entries"
        )

    def test_digit_entries_complete(self):
        """All digits 0-9 must be present in C++ table."""
        cpp_table = parse_cpp_table()

        digit_mappings = {
            0x7E: "0", 0x30: "1", 0x6D: "2", 0x79: "3", 0x33: "4",
            0x5B: "5", 0x5F: "6", 0x70: "7", 0x7F: "8", 0x73: "9",
        }

        for byte_val, expected_digit in digit_mappings.items():
            assert byte_val in cpp_table, (
                f"Digit '{expected_digit}' (0x{byte_val:02X}) missing from C++ table"
            )
            assert cpp_table[byte_val] == expected_digit, (
                f"Digit mismatch at 0x{byte_val:02X}: "
                f"expected '{expected_digit}', got '{cpp_table[byte_val]}'"
            )
