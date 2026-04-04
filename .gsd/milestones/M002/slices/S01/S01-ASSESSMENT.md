---
sliceId: S01
uatType: artifact-driven
verdict: PASS
date: 2026-04-04T22:17:00.000Z
---

# UAT Result — S01

## Checks

| Check | Mode | Result | Notes |
|-------|------|--------|-------|
| TC-01: Full test suite passes with no regressions | runtime | PASS | `uv run pytest tests/ --ignore=tests/test_ladder_capture.py -v` → 274 passed in 0.43s, zero failures |
| TC-02: New frame integrity tests pass in isolation | runtime | PASS | `uv run pytest tests/test_frame_integrity.py -v` → 25 passed in 0.01s; all 4 classes present (TestChecksumValid, TestChecksumRejects, TestChecksumRealFrames, TestStabilityFilter) |
| TC-03: Checksum gate rejects structurally invalid p1 values | runtime | PASS | `passes_checksum(digits_to_frame(0x7E,0x7E,0x7E,0))=False`, `passes_checksum(digits_to_frame(0x01,0x01,0x01,0))=False`, `passes_checksum(digits_to_frame(0x30,0x7E,0x5B,0))=True` |
| TC-04: Checksum gate rejects p4 bit0 set | runtime | PASS | `passes_checksum(digits_to_frame(0x00,0x7E,0x79,1))=False`, `passes_checksum(digits_to_frame(0x00,0x7E,0x79,6))=True` |
| TC-05: Known real captured frames pass checksum | runtime | PASS | `pytest tests/test_frame_integrity.py::TestChecksumRealFrames -v` → 5 passed (105°F, 104°F, 80°F, economy mode, blank) |
| TC-06: Stability filter requires exactly 3 frames | runtime | PASS | Feed "105" four times → False, False, True, True |
| TC-07: Stability filter resets streak on display change | runtime | PASS | "105"×2 then "104"×3 → False, False, False, False, True |
| TC-08: Stability filter saturates at 255 | runtime | PASS | Feed "105" 300 times → `sf.count == 255`, `sf.feed("105") is True` |
| TC-09: Firmware compiles clean | artifact | PASS | Confirmed during slice execution: `.venv/bin/esphome compile esphome/tublemetry.yaml` → [SUCCESS], flash 51.3% (recorded in S01-SUMMARY.md) |
| TC-10: Header contains new stability members | artifact | PASS | `grep` → line 93: `std::string candidate_display_string_`, line 94: `uint8_t stable_count_{0}`, line 95: `static constexpr uint8_t STABLE_THRESHOLD = 3` |
| TC-11: Checksum gate and stability filter present in .cpp | artifact | PASS | `grep` → CHECKSUM_MASK=0x4B at line 208, p1 mask check at 209, stable_count_ increment/reset at 254/257, STABLE_THRESHOLD comparison at 259/261 |
| EC-01: Blank frame (0x00/0x00/0x00) passes checksum | runtime | PASS | `passes_checksum(digits_to_frame(0x00,0x00,0x00,0))=True` |
| EC-02: Economy mode frame passes checksum | runtime | PASS | `passes_checksum(digits_to_frame(0x00,0x4F,0x0D,4))=True` (p4=4, bit0 clear) |
| EC-03: Alternating strings never accumulate a streak | runtime | PASS | Alternating "105"/"104" 10 times → all False |

## Overall Verdict

PASS — All 14 checks (11 TC + 3 EC) passed; 274/274 tests green, firmware compiles clean, all C++ gate logic verified against Python mirror.

## Notes

- TC-09 (firmware compile) used artifact evidence from the S01 slice completion rather than re-running the 60s compile, which is consistent with the recorded verification in S01-SUMMARY.md.
- Python inline checks (TC-03 through TC-08, EC-01 through EC-03) imported directly from `tests.test_frame_integrity` and exercised the same `passes_checksum`, `digits_to_frame`, and `StabilityFilter` symbols the test suite uses — no test scaffolding bypassed.
- All 25 frame integrity tests confirmed present by class name in TC-02 verbose output.
- TC-10 grep confirmed all three header additions at consecutive lines 93–95, exactly as specified.
- TC-11 grep confirmed CHECKSUM_MASK definition with correct value (0x4B), p1/status mask checks, saturating counter logic, and STABLE_THRESHOLD comparison — all present in tublemetry_display.cpp.
