---
estimated_steps: 39
estimated_files: 2
skills_used: []
---

# T02: Write test_frame_integrity.py and verify all tests pass

Write Python tests that mirror the C++ checksum and stability logic, then run the full test suite to confirm no regressions.

### Steps

1. Read `tests/test_mock_frames.py` to understand the available helpers (`frame_to_digits`, `frame_to_display_string`, `digits_to_frame`).
2. Create `tests/test_frame_integrity.py`. The tests mirror the C++ logic in Python — they do not invoke a C++ binary. Import helpers from `test_mock_frames` via direct import (both files are in the `tests/` package).
3. Implement a Python `passes_checksum(frame_bits)` helper that mirrors the C++ gate:
   ```python
   CHECKSUM_MASK = 0x4B
   def passes_checksum(frame_bits: int) -> bool:
       p1 = (frame_bits >> 17) & 0x7F
       p4 = frame_bits & 0x07
       return (p1 & CHECKSUM_MASK) == 0x00 and (p4 & 0x01) == 0x00
   ```
4. Implement a Python `StabilityFilter` class (or simple function) that mirrors the C++ filter:
   ```python
   STABLE_THRESHOLD = 3
   class StabilityFilter:
       def __init__(self): self.candidate = None; self.count = 0
       def feed(self, display_str: str) -> bool:  # returns True if should publish
           if display_str == self.candidate:
               if self.count < 255: self.count += 1
           else:
               self.candidate = display_str; self.count = 1
           return self.count >= STABLE_THRESHOLD
   ```
5. Write checksum tests:
   - `test_checksum_valid_blank`: `digits_to_frame(0x00, 0x7E, 0x79, 0)` → passes (blank hundreds, valid)
   - `test_checksum_valid_1_as_hundreds`: `digits_to_frame(0x30, 0x7E, 0x5B, 0)` → passes (p1='1')
   - `test_checksum_valid_1_variant`: `digits_to_frame(0x34, 0x7E, 0x5B, 0)` → passes (p1='1' alternate encoding)
   - `test_checksum_rejects_zero_display`: `digits_to_frame(0x7E, 0x7E, 0x7E, 0)` → fails (p1=0x7E has bits set in mask)
   - `test_checksum_rejects_startup_dash`: `digits_to_frame(0x01, 0x01, 0x01, 0)` → fails (p1=0x01 has bit0 set in mask)
   - `test_checksum_rejects_p4_bit0`: `digits_to_frame(0x00, 0x7E, 0x79, 1)` → fails (p4 bit0 set)
   - `test_checksum_allows_p4_bit1_bit2`: `digits_to_frame(0x00, 0x7E, 0x79, 6)` → passes (p4 bits 1,2 free)
6. Write stability filter tests:
   - `test_stability_two_frames_hold`: feed same string twice → returns False, False
   - `test_stability_three_frames_publish`: feed same string 3x → False, False, True
   - `test_stability_reset_on_change`: feed 'A' twice then 'B' → False, False, False (reset on 'B')
   - `test_stability_new_streak`: feed 'A' twice, 'B' three times → first B=False, second B=False, third B=True
   - `test_stability_saturation`: feed same string 300 times → count caps at 255, still publishes
7. Run `uv run pytest tests/ --ignore=tests/test_ladder_capture.py -v` and confirm all tests pass (249 + new).

## Inputs

- ``esphome/components/tublemetry_display/tublemetry_display.h` — STABLE_THRESHOLD=3, CHECKSUM_MASK=0x4B constants to mirror`
- ``esphome/components/tublemetry_display/tublemetry_display.cpp` — checksum and stability logic to mirror`
- ``tests/test_mock_frames.py` — frame_to_digits, digits_to_frame helpers to import`

## Expected Output

- ``tests/test_frame_integrity.py` — new test file with checksum and stability filter tests`

## Verification

uv run pytest tests/ --ignore=tests/test_ladder_capture.py -v 2>&1 | tail -10
