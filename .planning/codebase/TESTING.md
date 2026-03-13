# Testing Patterns

**Analysis Date:** 2026-03-13

## Current State: No Formal Testing Framework

**No tests detected in the codebase.** There are:
- No test files (no `*_test.py`, `test_*.py`, `*_spec.py`)
- No test configuration files (`pytest.ini`, `tox.ini`, `conftest.py`)
- No test dependencies in requirements or configuration files
- No CI/CD pipeline configuration

This is a **research/exploration codebase** where scripts are validation tools themselves.

## How Validation Currently Works

### 1. **Script as Self-Validating Tool**

Scripts are designed to produce **human-readable output** that confirms correctness. Validation is manual:

**Example: `bruteforce_7seg_v2.py`**
- Tests 40,320 bit-to-segment mappings
- Scores each mapping based on criteria:
  - Byte 3 changes between frames (temperature digit varies)
  - Both frames decode to valid digits 0-9
  - Temperature readings fall within 80-120°F range
  - Difference between frames is 1-10°F
- Outputs ranked solutions grouped by temperature
- User inspects output to confirm mapping is sensible

```python
score = decoded * 10 + digits * 5 + (50 if temp_valid else 0) + (30 if fe_is_8 else 0)

if score >= 100:  # reasonable threshold
    best_results.append((score, dp_bit, perm, mapping, decoded, digits, ...))

# Sort by score descending
best_results.sort(key=lambda x: -x[0])
```

**Example: `analyze_protocol.py`**
- Tests 4 candidate 7-segment mappings against all known data
- Decodes all unique byte values
- Outputs which bytes map to valid digits vs unknown segments
- User reviews output to assess mapping quality

```python
# Test specific candidate mappings
magnusper = {'a': 6, 'b': 5, 'c': 4, 'd': 3, 'e': 2, 'f': 1, 'g': 0}
test_mapping("MagnusPer (bit7=dp)", magnusper)

# Output shows which byte values decode to which characters
```

### 2. **Real-World Capture Validation**

Scripts validate against **actual hardware captures**:

**`rs485_capture.py` and `rs485_jets.py`**
- Record live serial data from hot tub controller
- User marks button presses interactively
- Output shows hexadecimal sequences for user inspection
- Saves to `.txt` files with timestamps and unique pattern counts

```python
# User marks event with input
marker = f"===== MARKER {marker_count}: [{user_input.strip()}] at {elapsed:.3f}s ====="
log.append(marker)

# Show unique patterns
for pat, count in sorted(unique_patterns.items(), key=lambda x: -x[1]):
    f.write(f"  {count:6d}x  {pat}\n")
```

User then compares patterns manually to understand protocol.

### 3. **Data Analysis & Inspection**

**`decode_7seg.py`**
- Processes 10M-row logic analyzer CSV files
- Performs signal analysis:
  - Transition detection
  - Burst segmentation
  - Polarity testing (idle-high vs idle-low UART)
  - Run-length encoding
- Outputs structured analysis:
  - Transition counts
  - Burst timing
  - Decoded byte sequences
  - Transition density patterns

User inspects to validate protocol understanding.

```python
# Burst analysis
bursts_fine = find_bursts(signal, min_gap_us=200, min_transitions=3)
print(f"Bursts (>200us gap): {len(bursts_fine)}")

# UART decode attempts
for polarity in ["idle_high", "idle_low"]:
    all_bytes = []
    for b_start, b_end in bursts_fine[:50]:
        decoded = uart_decode_region(signal, b_start, b_end, polarity)
        all_bytes.extend(decoded)

    if all_bytes:
        byte_counts = Counter(all_bytes)
        print(f"  Polarity: {polarity}")
        print(f"  Decoded {len(all_bytes)} bytes, {len(byte_counts)} unique")
```

## If Tests Were to Be Written

### Recommended Testing Approach

Given the **exploratory/research nature**, tests should focus on:

**1. Bit Manipulation & Encoding/Decoding**

Unit tests for core functions that don't require hardware:

```python
# Example test structure (using standard unittest or pytest)

def test_decode_byte_matches_known_values():
    """Test that known digit bytes decode correctly."""
    mapping = {'a': 6, 'b': 5, 'c': 4, 'd': 3, 'e': 2, 'f': 1, 'g': 7}

    # 7-segment encoding: digit "8" should light all 7 segments
    digit_8_byte = 0xFF  # all segment bits set
    char, dp, segs = decode_byte(digit_8_byte, mapping)
    assert char == '8'
    assert segs == frozenset('abcdefg')

def test_uart_decode_known_sequence():
    """Test UART decoding against known valid sequence."""
    # Known valid 115200 baud sequence
    signal = [...]  # pre-constructed valid UART signal
    result = uart_decode_region_idle_high(signal, 0, len(signal)-1)
    assert result == [0xFE, 0x06, 0x70, 0x30]

def test_find_bursts_detects_transitions():
    """Test burst detection."""
    # Construct signal with known burst pattern
    signal = [1,1,1,0,0,0,1,1,1] + [0]*1000 + [1,1,0,0,1,1]
    bursts = find_bursts(signal, min_gap_us=500, min_transitions=3)
    assert len(bursts) == 2
```

**2. Integration Tests Against Known Captures**

Test against saved `.txt` files (already in repo):

```python
def test_analyze_protocol_against_hex_capture():
    """Test protocol analysis against known capture data."""
    # Load known bytes from hex.txt
    PIN5_IDLE_A = [0xFE, 0x06, 0x70, 0x30, 0x00, 0x06, 0x70, 0x00]
    PIN5_IDLE_B = [0xFE, 0x06, 0x70, 0xE6, 0x00, 0x06, 0x70, 0x00]

    # Run best-scoring mapping
    mapping = find_best_mapping(PIN5_IDLE_A, PIN5_IDLE_B)

    # Verify byte 3 decodes to different digits
    char_a3 = decode_byte(0x30, mapping)[0]
    char_b3 = decode_byte(0xE6, mapping)[0]
    assert char_a3 in '0123456789'
    assert char_b3 in '0123456789'
    assert char_a3 != char_b3
```

**3. Brute-Force Validation**

Verify exhaustive search completeness:

```python
def test_brute_force_finds_known_solution():
    """Test that brute-force search finds the correct mapping."""
    solutions = run_brute_force_7seg()

    # Verify expected temperature range found
    temps = set((s['temp_a'], s['temp_b']) for s in solutions)
    assert any(80 <= t[0] <= 120 for t in temps)
    assert any(80 <= t[1] <= 120 for t in temps)

    # Verify at least one solution with reasonable score
    assert any(s['score'] >= 100 for s in solutions)
```

### Test Organization (If Implemented)

**File Structure:**
```
tubtron/
├── 485/
│   ├── scripts/
│   │   ├── rs485_scan.py
│   │   ├── decode_7seg.py
│   │   └── ...
│   └── tests/                    # New
│       ├── __init__.py
│       ├── test_bit_operations.py    # Bit/byte encoding tests
│       ├── test_uart_decode.py       # UART parsing tests
│       ├── test_7seg_mapping.py      # 7-segment mapping tests
│       └── fixtures/
│           ├── hex_capture.py        # Known byte sequences
│           └── signal_data.py        # Known signal patterns
```

**Test Naming Convention (if implemented):**
- `test_<function_name>_<scenario>`
- Example: `test_decode_byte_matches_known_values`, `test_find_bursts_detects_transitions`

### Coverage Targets (If Enforced)

If testing becomes formal:
- Core utilities (bit operations, encoding): 90%+ coverage
- Analysis functions (burst detection, UART decode): 75%+
- Brute-force search: Parametric testing of scoring logic
- **Not critical:** Interactive I/O (rs485_capture.py) - too tied to hardware

## Current Validation Method: Manual Inspection

**The codebase validates through:**

1. **Script Output Inspection**
   - Does the decoded data look reasonable?
   - Are temperatures in expected range (80-120°F)?
   - Do found byte patterns match hardware reality?

2. **Cross-Script Verification**
   - `decode_7seg.py` → finds burst patterns
   - `analyze_protocol.py` → tests 4 candidate mappings against patterns
   - `bruteforce_7seg_v2.py` → exhaustive search confirms best mapping
   - All three should converge on same answer

3. **Real Hardware Testing**
   - Capture scripts (`rs485_capture.py`, `rs485_jets.py`) record actual device behavior
   - User presses buttons, captures output
   - Compare against expected protocol sequences

4. **Data Consistency Checks**
   - Byte 3 changes between frames (temperature varies) ✓
   - Bytes 0-2 constant (display digits for 1, 0, indicator) ✓
   - Temperature range 80-120°F ✓
   - Found byte values match all 3 capture sources ✓

## Recommendations for Future Testing

**If moving toward automated testing:**

1. **Start with unit tests** for bit/byte manipulation functions
   - No external dependencies
   - Fast execution
   - High confidence in core logic

2. **Add parametric tests** for brute-force exhaustiveness
   - Verify all 40,320 combinations tested
   - Verify scoring logic is deterministic

3. **Save golden outputs** from known-good runs
   - Use for regression testing when refactoring
   - Document expected behavior of analysis scripts

4. **Consider property-based testing** (hypothesis library)
   - Test that bit mappings are reversible
   - Test that all valid digits are decodable

5. **Document test expectations in comments**
   - Why certain temperature ranges are valid
   - What byte patterns should/shouldn't appear

---

*Testing analysis: 2026-03-13*
