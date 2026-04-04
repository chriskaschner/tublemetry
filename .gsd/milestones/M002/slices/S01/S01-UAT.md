# S01: Frame Integrity — Checksum + Stability Filter — UAT

**Milestone:** M002
**Written:** 2026-04-04T13:39:50.036Z

## UAT: S01 — Frame Integrity

### Preconditions
- Working directory: repo root (or worktree)
- `uv` available; Python deps installed (`uv sync`)
- ESPHome venv available at `.venv/bin/esphome`
- `secrets.yaml` symlinked or present in `esphome/`

---

### TC-01: Full test suite passes with no regressions

**Purpose:** Confirm S01 changes don't break any existing test.

**Steps:**
1. Run `uv run pytest tests/ --ignore=tests/test_ladder_capture.py -v`
2. Observe final line of output

**Expected:** `274 passed` (or higher if more tests exist). Zero failures, zero errors.

---

### TC-02: New frame integrity tests pass in isolation

**Purpose:** Confirm the 25 new tests execute correctly on their own.

**Steps:**
1. Run `uv run pytest tests/test_frame_integrity.py -v`
2. Observe output

**Expected:** `25 passed` in <1s. All test names appear (TestChecksumValid, TestChecksumRejects, TestChecksumRealFrames, TestStabilityFilter).

---

### TC-03: Checksum gate rejects structurally invalid p1 values

**Purpose:** Verify the gate catches the most common corruption pattern — hundreds digit byte with reserved bits set.

**Steps:**
1. In a Python REPL or test: `from tests.test_frame_integrity import passes_checksum, digits_to_frame` (via tests package import)
2. Check `passes_checksum(digits_to_frame(0x7E, 0x7E, 0x7E, 0))` → should be `False` (hundreds='0', bit6 set)
3. Check `passes_checksum(digits_to_frame(0x01, 0x01, 0x01, 0))` → should be `False` (startup dash, bit0 set)
4. Check `passes_checksum(digits_to_frame(0x30, 0x7E, 0x5B, 0))` → should be `True` (valid 105°F frame)

**Expected:** False, False, True respectively.

---

### TC-04: Checksum gate rejects p4 bit0 set

**Purpose:** Verify p4 check is independent of p1.

**Steps:**
1. `passes_checksum(digits_to_frame(0x00, 0x7E, 0x79, 1))` — valid p1, p4=0b001
2. `passes_checksum(digits_to_frame(0x00, 0x7E, 0x79, 6))` — valid p1, p4=0b110 (bits 1,2 ok)

**Expected:** False, True.

---

### TC-05: Known real captured frames pass checksum

**Purpose:** Confirm the gate is structurally compatible with actual wire data — not overly restrictive.

**Steps:**
1. Run `uv run pytest tests/test_frame_integrity.py::TestChecksumRealFrames -v`

**Expected:** All 5 tests pass (105°F, 104°F, 80°F, economy mode, blank).

---

### TC-06: Stability filter requires exactly 3 frames

**Purpose:** Verify threshold boundary — 2 frames hold, 3rd publishes.

**Steps:**
1. `from tests.test_frame_integrity import StabilityFilter`
2. `sf = StabilityFilter()`
3. `sf.feed("105")` → `False`
4. `sf.feed("105")` → `False`
5. `sf.feed("105")` → `True`
6. `sf.feed("105")` → `True` (continues publishing)

**Expected:** False, False, True, True.

---

### TC-07: Stability filter resets streak on display change

**Purpose:** Verify that a new display value resets the counter.

**Steps:**
1. `sf = StabilityFilter()`
2. Feed `"105"` twice → both `False`
3. Feed `"104"` → `False` (streak reset, count=1 for "104")
4. Feed `"104"` twice more → `False`, `True`

**Expected:** False, False, False, False, True.

---

### TC-08: Stability filter saturates at 255

**Purpose:** Verify no uint8 overflow on long-running stable display.

**Steps:**
1. `sf = StabilityFilter(); [sf.feed("105") for _ in range(300)]`
2. Check `sf.count == 255`
3. Check `sf.feed("105") is True`

**Expected:** count=255, still publishes.

---

### TC-09: Firmware compiles clean

**Purpose:** Confirm C++ changes compile without errors or warnings.

**Steps:**
1. Run `.venv/bin/esphome compile esphome/tublemetry.yaml`
2. Observe final lines

**Expected:** `[SUCCESS]` with `Successfully compiled program.` Flash usage ~51%.

---

### TC-10: Header contains new stability members

**Purpose:** Spot-check that the header additions are present and correctly typed.

**Steps:**
1. `grep -n "candidate_display_string_\|stable_count_\|STABLE_THRESHOLD" esphome/components/tublemetry_display/tublemetry_display.h`

**Expected:** Three matches — `std::string candidate_display_string_`, `uint8_t stable_count_{0}`, `static constexpr uint8_t STABLE_THRESHOLD = 3`.

---

### TC-11: Checksum gate and stability filter present in .cpp

**Purpose:** Confirm both logic blocks are present in the implementation.

**Steps:**
1. `grep -n "CHECKSUM_MASK\|stable_count_\|STABLE_THRESHOLD" esphome/components/tublemetry_display/tublemetry_display.cpp`

**Expected:** Multiple matches — CHECKSUM_MASK definition, stable_count_ increment/reset, STABLE_THRESHOLD comparison.

---

### Edge Cases

**EC-01: Blank frame (0x00/0x00/0x00) passes checksum**
- `passes_checksum(digits_to_frame(0x00, 0x00, 0x00, 0))` → `True`
- Blank displays are valid steady states (e.g. during setpoint flash), must not be filtered.

**EC-02: Economy mode frame passes checksum**
- `passes_checksum(digits_to_frame(0x00, 0x4F, 0x0D, 4))` → `True`
- p4=4 (0b100, bit0 clear) is valid; economy mode must reach the display state classifier.

**EC-03: Alternating strings never accumulate a streak**
- Feed alternating "105"/"104" 10 times — all return False.
- Stability filter correctly resets on every change, never reaching threshold.

