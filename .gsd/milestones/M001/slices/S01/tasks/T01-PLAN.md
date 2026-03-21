# T01: 01-button-injection-mvp 01

**Slice:** S01 — **Milestone:** M001

## Description

Build the Python decode library for the VS300FL4 RS-485 display stream. This is the core logic that converts raw UART bytes into meaningful display readings (temperature, OH, ICE, etc.).

Purpose: The decode logic must be correct before porting to C++ for the ESPHome component. Python enables thorough TDD with fast iteration. The 7-segment lookup table uses confirmed mappings (0x30="1", 0x70="7") and placeholders for unverified bytes that will be filled in after the temperature ladder capture.

Output: A tested Python library (`src/tubtron/`) with three modules -- `decode.py` (7-segment lookup), `frame_parser.py` (8-byte frame parsing), `display_state.py` (state machine for temperature persistence). All exercised by pytest tests.

## Must-Haves

- [ ] "Known byte values (0x30, 0x70, 0x00) decode to correct characters (1, 7, blank)"
- [ ] "An 8-byte idle frame is parsed into a display string"
- [ ] "Non-temperature display strings (OH, ICE, --) are detected and classified"
- [ ] "Last valid temperature persists when display shows non-temperature state"
- [ ] "All decode logic is exercised by automated tests"

## Files

- `pyproject.toml`
- `tests/conftest.py`
- `tests/test_decode.py`
- `tests/test_frame_parser.py`
- `tests/test_display_state.py`
- `src/tubtron/__init__.py`
- `src/tubtron/decode.py`
- `src/tubtron/frame_parser.py`
- `src/tubtron/display_state.py`
