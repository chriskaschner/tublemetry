# Coding Conventions

**Analysis Date:** 2026-03-13

## Language & Runtime

**Primary Language:** Python 3

**No formal configuration files** (pyproject.toml, setup.py, pytest.ini) detected. This is a research/exploration codebase.

## Naming Patterns

**Files:**
- Snake case with descriptive names: `rs485_scan.py`, `decode_7seg.py`, `bruteforce_7seg_v2.py`
- Versioning convention: v1 → v2 suffix indicates major revisions: `bruteforce_7seg.py` vs `bruteforce_7seg_v2.py`
- Functional grouping: scripts are organized by purpose (scan, capture, decode, brute-force analysis)

**Functions & Methods:**
- Snake case throughout: `find_bursts()`, `uart_decode_region()`, `analyze_channel()`, `decode_byte()`
- Verb-first naming convention: `decode_`, `find_`, `build_`, `test_`, `analyze_`
- Helper functions use descriptive prefixes: `decode_uart_idle_high()`, `decode_uart_idle_low()`

**Variables:**
- Snake case for all variable names: `SAMPLE_RATE`, `BAUD_RATES`, `total_bytes`, `hex_str`, `input_queue`
- Constants are UPPER_CASE with underscores: `SAMPLE_RATE = 1_000_000`, `PORT = "COM9"`, `LISTEN_SECONDS = 3`
- Loop counters use single letters: `i`, `j`, `b`, `t`, `w`
- Temporary/working variables: `bv` (byte value), `ch` (channel), `dp` (decimal point)

**Types & Data Structures:**
- No type hints observed in the codebase
- Dictionary keys are typically lowercase strings or descriptive tuples: `{'mapping': ..., 'dp_bit': ..., 'temp_a': ...}`
- Lists/arrays use descriptive names: `solutions`, `decoded`, `digits_a`, `phase_boundaries`

## Code Style

**Formatting:**
- 4-space indentation (Python standard)
- Line length appears to follow conventional Python limits (readable, no strict enforcement)
- Vertical spacing: Single blank lines between logical sections, double blank lines between major blocks
- String formatting: Mix of f-strings (modern) and format() method
  - Preferred: `f"{b:02X}"` for hex output, `f"[{elapsed:8.3f}]"` for formatted output
  - Format method: `"".format()` used occasionally in older scripts

**Comments:**
- Single-line comments use `#` with space: `# Calculate bit positions`
- Docstrings in triple quotes used for function documentation:
  ```python
  def find_bursts(signal, min_gap_us=500, min_transitions=5):
      """Find bursts of activity in a signal.
      A burst is a region with transitions, separated by gaps...
      Returns list of (start_idx, end_idx) tuples.
      """
  ```
- Inline comments describe non-obvious logic: `# Flush any stale data`, `# Only print lines that differ from idle pattern`

**Imports:**
- Standard order observed:
  1. Standard library: `import os`, `import csv`, `import serial`, `import time`, `import sys`, `import threading`, `import queue`
  2. Third-party packages: `import numpy as np` (from `itertools`)
- Imports at top of file, followed by constants, then functions

## Import Organization

**Standard Library First:**
```python
import serial
import sys
import time
import threading
import queue
```

**Third-Party Packages:**
```python
import numpy as np
from itertools import permutations, combinations
from collections import Counter, defaultdict
```

**Path Aliases:**
- No aliases detected (no config files)
- Direct imports of standard modules

**Constants After Imports:**
```python
BAUD_RATES = [1200, 2400, 4800, ...]
PORT = "COM9"
LISTEN_SECONDS = 3
SAMPLE_RATE = 1_000_000
```

## Error Handling

**Exception Handling Patterns:**
- Specific exception catching (not bare `except:`)
  ```python
  except serial.SerialException as e:
      print(f"\n>> {baud} baud — ERROR: {e}")
  except KeyboardInterrupt:
      print("\nStopped by user.")
      sys.exit(0)
  ```
- User-friendly error messages with context
- Graceful shutdown on keyboard interrupt (Ctrl+C)

**Data Validation:**
- Guard clauses for edge cases: `if len(transitions) == 0: return []`
- Bounds checking in loops: `if i < n - int(SPB * 10)`, `if pos >= n:`
- Type checking before operations: `if len(bursts_fine) == 0:`, `if all_bytes:`

**Error Recovery:**
- Continue on error rather than hard exit (when appropriate)
- Resource cleanup: `ser.close()` always called, even in error paths
- Thread management: daemon threads used for background input: `t = threading.Thread(target=input_thread, daemon=True)`

## Function Design

**Size & Scope:**
- Functions are typically 15-50 lines, focused on single responsibilities
- Exception: Analysis scripts like `analyze_channel()` can be 100+ lines when performing many sequential analysis steps
- Helpers extracted when logic repeats: `decode_byte()`, `build_lookup()`, `make_mask()`

**Parameters:**
- Explicit keyword arguments for configuration: `min_gap_us=500, min_transitions=5, polarity="idle_high"`
- Default values provided for optional parameters
- Multiple parameters grouped logically: `bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE`

**Return Values:**
- Tuples for multiple returns: `return (start_idx, end_idx)`, `return char, dp_val, active_segments`
- Lists for collections: `return decoded` (list of bytes)
- Single values when appropriate: `return len(solutions)`
- Early returns for edge cases: `if len(transitions) == 0: return []`

**Tuple Returns (Multiple Values):**
```python
# Example from decode_byte():
return char, dp_val, active  # Returns (str/None, bool, frozenset)

# Example from find_bursts():
bursts.append((transitions[start], transitions[end - 1]))  # (start_idx, end_idx)
```

## Module Design

**No Package Structure:**
- Scripts are standalone, run directly as main programs
- No `__init__.py` files or module hierarchy
- Each script is self-contained with its own constants, functions, and main execution

**Script Patterns:**
- Print-heavy approach for output and logging
- Interactive mode common: `input()`, threading.Queue for non-blocking input
- File output: Plain text logs saved to `.txt` files: `rs485_capture.txt`, `rs485_jets.txt`

**Data Flow:**
- Top-level constants → Function definitions → Main execution block
- No conditional `if __name__ == "__main__":` blocks observed (scripts assume direct execution)

**Utility Patterns:**
- Reusable functions extracted: `uart_decode_region()` used in multiple contexts
- Lookup tables built dynamically: `build_lookup()` creates byte-to-digit mappings
- Bit manipulation helpers: `make_mask()` creates bitmasks from bit positions

## Logging & Output

**Framework:** No formal logging module. Uses `print()` statements directly.

**Patterns:**
- Status messages with timestamps: `print(f"[{elapsed:8.3f}] Listening...")`
- Section headers with visual separators: `print("=" * 70)`
- Formatted tables: `print(f"{offset:04X}  {hex_part:<48s}  {ascii_part}")`
- Progress reporting in loops: `if count % 10000 == 0: print(f"  Checked {count}...")`

**Output Destinations:**
- Console (stdout): Real-time data and status
- Files: Capture logs saved to `.txt`: `with open(outfile, "w") as f:`
- No separate stderr; all output to stdout

## Code Patterns Observed

**Byte/Hex Manipulation:**
- Hex formatting: `f"{b:02X}"` (2-digit uppercase hex)
- Binary formatting: `f"{val:08b}"` (8-bit binary)
- Bit operations: `byte_val |= (1 << bit_idx)` (set bit), `bool(bv & (1 << bit))`
- Masking: `val = bv & seg_mask` (extract bits)

**Itertools Usage:**
```python
from itertools import permutations, combinations
for bit_combo in combinations(range(8), 7):
    for bit_perm in permutations(bit_combo):
        # Test all permutations
```

**Dictionary Comprehensions & Defaultdict:**
```python
DIGIT_SEGMENTS = {
    '0': frozenset('abcdef'),
    '1': frozenset('bc'),
    # ...
}

by_temps = defaultdict(list)
for s in solutions:
    by_temps[(s['temp_a'], s['temp_b'])].append(s)
```

**Data Analysis Patterns:**
- Bit field extraction and analysis
- Brute-force search over parameter spaces (40,320+ combinations tested)
- Score-based ranking of candidate solutions
- Signal processing: transition detection, burst segmentation, run-length encoding

## Observations & Deviations

**No Style Guide Enforcement:**
- No `.pylintrc`, `.flake8`, `ruff.toml`, or similar
- Conventions emerge from natural Python practices and repeated patterns
- No strict formatting (no Black or isort usage)

**Pragmatic Approach:**
- Scripts prioritize functionality over strict code architecture
- Print-driven rather than structured logging
- Single-file scripts designed for one-off execution
- Optimization for readability in exploratory/research context

---

*Convention analysis: 2026-03-13*
