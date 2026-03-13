# Architecture

**Analysis Date:** 2026-03-13

## Pattern Overview

**Overall:** Hardware reverse-engineering with layered analysis tools

The codebase is organized as a research/reverse-engineering project focused on understanding the RS-485 communication protocol used by Balboa VS300FL4 hot tub controllers. The architecture follows a progressive discovery pattern: from raw protocol capture, through signal analysis, to 7-segment display decoding and protocol interpretation.

**Key Characteristics:**
- Sequential tools that build on each other (capture → analysis → decoding)
- Data-driven approach: captures stored as text logs and CSV files, scripts analyze them offline
- Focus on signal-level interpretation: UART decoding, burst pattern analysis, bit-level segment mapping
- Research-oriented: multiple experimental approaches and brute-force search techniques
- Hardware bridging: USB RS-485 adapters connected to Balboa RJ45 connectors, logic analyzer captures

## Layers

**Capture Layer:**
- Purpose: Raw data acquisition from Balboa VS300FL4 control board via RS-485
- Location: `485/scripts/rs485_capture.py`, `485/scripts/rs485_scan.py`, `485/scripts/rs485_jets.py`
- Contains: Serial port communication, baud rate scanning, interactive button press marking
- Depends on: `pyserial` library, COM9 USB RS-485 adapter
- Used by: Analysis layer (data sources)
- Output: Text log files with timestamped hex dumps and marker annotations (e.g., `rs485_capture.txt`, `rs485_jets.txt`)

**Analysis & Preprocessing Layer:**
- Purpose: Extract patterns, decode UART frames, identify frequency/timing characteristics
- Location: `485/scripts/analyze_protocol.py`, `485/scripts/decode_csv.py`, `485/scripts/decode_7seg.py`
- Contains: Burst detection, UART frame decoding (both polarities), run-length encoding, transition analysis
- Depends on: Text capture files, logic analyzer CSV exports (e.g., `254.csv`, `OH.csv`)
- Used by: Decoding layer
- Output: Structured byte sequences, frame boundaries, timing annotations

**Decoding Layer:**
- Purpose: Map raw bytes to 7-segment display values and interpret protocol semantics
- Location: `485/scripts/bruteforce_7seg.py`, `485/scripts/bruteforce_7seg_v2.py`, `485/scripts/analyze_protocol.py`
- Contains: Segment-to-bit mapping permutations, character lookup tables, temperature value interpretation
- Depends on: Analyzed byte sequences, known reference frames (Frame A, Frame B, temp-change frames)
- Used by: Protocol interpretation
- Output: Decoded characters, temperature values, protocol message structures

**Protocol Interpretation Layer:**
- Purpose: Understand command/status semantics and message structures
- Location: `485/README.md`, `485/scripts/analyze_protocol.py`, research notes
- Contains: Message type identification (idle frame vs. burst), FE byte status indicator, button command signatures
- Depends on: Decoded bytes and timing information
- Used by: Documentation and future implementation planning
- Output: Protocol specifications and command mappings

## Data Flow

**Hardware-to-Understanding Flow:**

1. **Capture Phase:** RS-485 adapter taps Balboa RJ45 connector (one wire pair at a time)
   - Initiated by: `rs485_capture.py` (interactive with button press markers) or `rs485_scan.py` (automated baud discovery)
   - Output: Text log file with timestamps and hex dumps (e.g., `rs485_capture.txt`)

2. **Signal Analysis Phase:** Raw text logs converted to structured byte sequences
   - Input: `rs485_capture.txt`, `rs485_jets.txt`, teraterm captures, logic analyzer CSV
   - Process: `decode_csv.py` performs UART decode (idle_high/idle_low) on logic analyzer data; manual analysis on text logs
   - Output: Isolated byte frames, confirmed baud rate (115200), identified bursts and idle patterns

3. **Display Decoding Phase:** Bytes mapped to 7-segment characters via exhaustive search
   - Input: Known reference frames (Frame A: `FE 06 70 30 00 06 70 00`, Frame B: `FE 06 70 E6 00 06 70 00`)
   - Process: `bruteforce_7seg.py` tries all 8 * 7! = 40,320 possible segment-to-bit mappings
   - Scoring: Valid temperature readings, FE decoding as '8', overall decode coverage
   - Output: Best-fit mapping and decoded characters for all bytes

4. **Protocol Interpretation:** Button press responses correlated with display changes
   - Input: Byte sequences with timestamps and button press markers
   - Analysis: Temp down (`00 06 00 F3`), temp up (`00 03 18 00`), lights toggle (FE disappears), jets (no change detected)
   - Output: Protocol specifications documented in README

**State Management:**
- No persistent state in code — each analysis script reads files independently
- State lives in: captured text files, CSV exports, reference frame definitions (hardcoded in scripts)
- Progression tracked by: file timestamps and WORKLOG.md annotations

## Key Abstractions

**Frame Definition:**
- Purpose: Encodes a single status message from board to panel
- Examples: Idle frames (8 bytes), burst patterns (11 bytes), temp-change frames (8 bytes)
- Pattern: Fixed byte sequences with status/temperature information encoded in specific positions
- Idle frame structure:
  ```
  [FE] [06] [70] [XX] [00] [06] [70] [00]
   |    |    |    |    |    |    |    |
   |    |    |    +-- Temperature digit (changes with temp)
   |    +------------ Display digit (constant in idle, changes with buttons)
   +----------------- Status/indicator (disappears when lights toggle)
  ```

**7-Segment Mapping:**
- Purpose: Convert byte value to displayable character via bit-to-segment assignment
- Pattern: Each byte is 8 bits; 7 bits map to segments (a-g), 1 bit is decimal point or unused
- Search space: 8 choices for dp bit × 7! = 40,320 possible mappings
- Scoring criteria: Maximize decoding coverage, validate temperature readings, check special cases (FE='8', OH error)

**Button Command Signature:**
- Purpose: Identify which button was pressed based on byte changes
- Pattern: Temperature/lights changes show in status frame; jets show no visible change (on separate wire pair)
- Examples:
  - Temp down: byte 5-7 change to `06 00 F3`, accompanied by burst pattern `E6 77 E6 E6 77 E6 E6 77 E6 E0 FF`
  - Temp up: byte 5-7 change to `03 18 00`, accompanied by burst pattern
  - Lights: FE byte disappears entirely, returns after ~2.5s

**Wire Pair Mapping:**
- Purpose: Correlate RS-485 adapter connections to logical data streams
- Pattern: Balboa uses 4 pairs in RJ45; 2 pairs are power/ground, 2 are data
- Current knowledge: One pair carries board→panel status (captured), other carries panel→board commands (not yet captured)
- Implementation: Manual voltage/resistance checks to identify pairs, then connect RS-485 A/B terminals

## Entry Points

**User-Interactive Capture:**
- Location: `485/scripts/rs485_capture.py`
- Triggers: User runs script on Windows machine with USB RS-485 adapter on COM9
- Responsibilities:
  - Opens serial port, listens continuously
  - Accepts user input (button names) to mark events in real-time
  - Saves timestamped hex log and unique pattern summary
  - Prompts user through capture session

**Automated Baud Rate Scanner:**
- Location: `485/scripts/rs485_scan.py`
- Triggers: User runs script to discover active baud rates on unknown port
- Responsibilities:
  - Tries 12 common baud rates sequentially (1200 to 921600)
  - Reports byte counts and first 128 bytes for each rate
  - Helps identify which rate produces coherent data

**Analysis & Decoding Scripts:**
- Location: `485/scripts/analyze_protocol.py`, `485/scripts/bruteforce_7seg*.py`, `485/scripts/decode_csv.py`
- Triggers: User runs script to re-analyze existing capture files (offline)
- Responsibilities:
  - Load capture data from disk
  - Perform exhaustive search or pattern matching
  - Output findings to stdout and optionally save refined data

## Error Handling

**Strategy:** Graceful degradation; report what could be decoded, skip what couldn't

**Patterns:**
- Missing stop bits in UART frames: Record byte value, note as framing error, continue
- Unmapped byte values (no 7-segment match): Display as '?' in output, increment undecodable count
- Invalid mappings: Return score of 0, skip in best-results ranking
- Serial port errors: Catch and report, allow user to retry or choose different port/baud
- File not found errors: Caught at startup (e.g., CSV path hardcoded with OneDrive prefix), user must adjust path

## Cross-Cutting Concerns

**Logging:**
- Approach: Stdout print statements, file writes at end of analysis
- Pattern: Progress indicators during capture (`[TIME] (BYTES bytes) HEX`), summary tables after completion
- Debug output: Unique pattern counts, transition statistics, decode coverage metrics

**Validation:**
- Approach: Heuristic scoring (decode coverage, digit validity, FE as '8', temperature range checks)
- Pattern: Multiple scoring criteria combined additively to identify best mappings
- Constraints: Temperature range 80-106°F (3 digits), OH error code recognized, FE byte usually present

**Hardware Configuration:**
- Approach: COM port and baud rate hardcoded in scripts; paths hardcoded in analysis scripts
- Pattern: PORT = "COM9", BAUD = 115200, CSV path = Windows OneDrive-specific path
- Flexibility: User must edit script to change; future work would use config file or CLI args

## Timing and Synchronization

**RS-485 Protocol Timing:**
- Baud rate: 115200 (verified)
- Data format: 8N1 (verified)
- Frame structure: Idle frame repeats every ~100ms; bursts appear on button press with ~200-2500ms delays depending on button
- Synchronization: Two wire pairs (status and commands) assumed to be synchronized by board logic; exact handshake not yet captured

**Display Refresh:**
- Idle: FE byte present, steady state
- Button press: Burst pattern appears (~10-11 bytes), alternates with modified idle frame
- Recovery: Returns to pure idle frame after 1-5 seconds depending on button
- Lights special case: FE disappears while lights active, reappears after timeout

---

*Architecture analysis: 2026-03-13*
