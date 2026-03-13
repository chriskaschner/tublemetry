# Codebase Concerns

**Analysis Date:** 2026-03-13

## Data Loss — Critical Issue

**Original Pin 5 button-press capture overwritten:**
- Files: `485/rs485_capture.txt`
- Impact: The file was meant to capture button press responses on the VS300FL4's Pin 5 (display content RS-485 channel), but has been overwritten with Pin 6 (display refresh) data instead. This is the only capture from the control board's response to button presses.
- Current state: `485/rs485_jets.txt` contains reliable Pin 5 idle data (285 frames, zero variation), but no button-press sequence.
- Recovery path: Must re-capture with the hot tub on-site. Connect RS-485 adapter to Pin 5, press Temp Up/Down/Lights/Jets buttons, save captures to separate files with clear naming (e.g., `rs485_pin5_tempminus.txt`). Takes ~30 minutes with proper labeling.
- Workaround: Current analysis scripts (`bruteforce_7seg.py`, `bruteforce_7seg_v2.py`) can still infer 7-segment encoding from idle frames and temp-change signatures noted in documentation, but cannot verify button press timing or command structure without the capture.

## Data Ambiguity — 7-Segment Encoding Unresolved

**72 candidate solutions for 7-segment display mapping:**
- Files: `485/scripts/bruteforce_7seg_v2.py` (produces ~72 solutions), `485/bruteforce_7seg.py` (alternative approach)
- Problem: Two bytes in the idle frame differ (byte 3: `0x30` in one capture vs `0xE6` in another), representing different temperatures. Without knowing the actual temperatures at capture time, the correct segment-to-bit mapping cannot be determined.
- Impact: Cannot decode display data for Phase 2 (closed-loop control). The brute force identified multiple mappings that satisfy "change represents 1-10°F difference" constraint, but all 72 are equally valid mathematically.
- Required fix: Capture Pin 5 data at 5+ known temperatures (104F → 103F → 102F → etc.). This physical measurement resolves the ambiguity by anchoring the encoding. Must be done at the hot tub.
- Current blockers:
  - Task 5 "Temperature ladder capture" in `.continue-here.md` explicitly calls this out as a blocker for Phase 2
  - This was anticipated in the design — it's listed as a prerequisite, not a surprise

## Untested Analysis Scripts — No Validation

**All 12 reverse-engineering scripts are research-grade, not production code:**
- Files: `485/scripts/*.py` (all)
- Pattern: Scripts decode captures, run brute-force searches, and produce theoretical solutions, but have no unit tests or validation against known-good output.
- Risk areas:
  - `decode_7seg.py` (311 lines): Uses numpy to load 10M-row CSV, decodes UART at variable sample rates. No error handling for malformed CSV or incomplete UART frames. Falls through on framing errors instead of flagging them.
  - `bruteforce_7seg_v2.py` (261 lines): Exhaustive P(8,7)=40,320 permutation search. No verification that solutions are actually correct beyond the constraints (temperature range 80-120F, 1-10F difference between frames).
  - `analyze_protocol.py` (306 lines): Hardcoded file paths (`C:\Users\ckaschner\...`). Will fail on any other machine. No path validation.
  - `decode_csv.py` (113 lines): Assumes specific OneDrive folder structure (`OneDrive - Electronic Theatre Controls, Inc`). Fails silently if file not found instead of reporting error.
  - All scripts assume Windows paths (`os.environ["USERPROFILE"]`, `C:\`). Not portable to Linux/macOS development.
- Testing debt: These scripts have intrinsic value for understanding the protocol but are not maintainable without tests. If display decoding needs to be integrated into firmware, the logic will need to be rewritten with proper error handling and test coverage.
- Mitigation: Current phase (Task 1 firmware config) doesn't depend on these. Phase 2 (display reading) will need a clean rewrite of the decoding logic in C++/ESPHome format with proper validation.

## Hardcoded Paths and Platform Assumptions

**Analysis scripts contain Windows-specific paths:**
- Files: `485/scripts/decode_7seg.py`, `485/scripts/decode_csv.py`, `485/scripts/analyze_protocol.py`
- Pattern:
  ```python
  # decode_7seg.py line 11:
  CSV_PATH = r"C:\Users\ckaschner\OneDrive - Electronic Theatre Controls, Inc\Desktop\485\OH.csv"
  # decode_csv.py lines 2-3:
  filepath = os.path.join(os.environ["USERPROFILE"], "OneDrive - Electronic Theatre Controls, Inc", ...)
  ```
- Impact: Scripts only run on the original Windows machine. Non-portable. If the project is shared or run on Linux for CI/analysis, these will fail.
- Fix approach: Use relative paths from project root (e.g., `./485/OH.csv`) or environment variable override (e.g., `DATA_DIR` env var). Not urgent since these are research-only scripts.

## Incomplete Test Plan for Button Timing

**Phase 1 Task 3 "Characterize button press timing" lacks predefined success criteria:**
- Files: `.planning/phases/01-button-injection-mvp/.continue-here.md` (task 3 description)
- Issue: The task description says "min press duration, inter-press gap, auto-repeat threshold" but doesn't specify acceptance criteria (e.g., "min press ≥ 50ms observed in N=10 trials, std dev < 10ms"). Without clear criteria, testing could be subjective.
- Fix approach: Add timing test matrix to WORKLOG.md before starting task 3:
  - Single press timing (measure delay from GPIO high to visible setpoint change)
  - Repeat interval (how fast can consecutive presses fire)
  - Hold duration (how long does button need to stay pressed to register)
  - Multi-press sequence (re-home sequence: 25 presses down → verify floor at 80F)

## Phase 2 Display Reading Dependency Chain

**Phase 2 (display stream decoding) has three unmet prerequisites:**
- Files: All in `485/scripts/`
- Blockers in order:
  1. **7-segment encoding:** Requires temperature ladder capture (on-site task)
  2. **Display multiplexing model:** Partially documented in `rs485-status-2026-03-08.md` but not validated against actual capture
  3. **Protocol state machine:** No documented state transitions for display updates (e.g., "what happens to the stream when temp changes?")
- Risk: Phase 2 was planned as "Phase 1.5" for good reason — open-loop control (Phase 1) cannot run unattended without display feedback. If temperature ladder capture is skipped, Phase 2 will be blocked indefinitely.

## NoSQL-like Data Storage Risk

**Analysis results scattered across files with no index:**
- Files:
  - `485/rs485_capture.txt` — Pin 6 refresh data
  - `485/rs485_jets.txt` — Pin 5 idle data (reliable)
  - `485/hex.txt` — Unknown (not examined)
  - `485/9600.txt` — Unknown
  - `485/teraterm.txt` — TeraTerm log (unstructured)
  - `reference/status_03_08.md` — Original findings
  - `485/rs485-status-2026-03-08.md` — Comprehensive analysis (best reference currently)
- Problem: No metadata file listing what each capture contains, when it was taken, which pins, what was being tested. The `.continue-here.md` notes that `rs485_capture.txt` was "OVERWRITTEN" — indicating this happened without tracking which file was overwritten or what was lost.
- Fix approach: Create `485/CAPTURES_INDEX.md` with table: filename, date, pins tested, button presses, known temp at capture time, notes. Makes future captures traceable and prevents accidental overwrites.

## Missing Validation of Manual Button Simulation

**Initial proof-of-concept (manual button press) is not documented with measured results:**
- Files: `485/rs485-status-2026-03-08.md` (lines 58-66)
- What was tested: "Briefly bridging Pin 1 (+5V) to Pin 8 (Temp Down) successfully lowered the displayed temperature setpoint by 1°F"
- What's missing:
  - How long was "briefly"? (Doesn't matter for proof-of-concept, critical for firmware timing)
  - How was the setpoint change observed? (Manual reading from display? Display capture?)
  - Was it a single press or multiple? How many presses to see 1°F change?
  - Did the board acknowledge the press (status change on RS-485)?
- Risk: Firmware task (Task 1) will need to define GPIO timing. Without baseline data from the manual test, timing estimates are guesses.
- Mitigation: Task 2 (breadboard prototype) should repeat the measurement with a timer/logic analyzer to get quantified baseline.

## Photorelays May Require Timing Validation

**Chosen component (AQY212EH) has 25Ω on-resistance but rise/fall time not explicitly verified for this application:**
- Files: `.continue-here.md` (hardware decision)
- Concern: The component specs on-resistance, but the board's analog button input has high impedance (idle ~2.3V divider). The photorelays' 25Ω may be low enough to pull the line to true logic-high (>4.5V), or might leave it at intermediate voltage depending on the divider network.
- Fix approach: Task 2 (breadboard build) includes empirical characterization. Can measure with multimeter before firmware work.

## Analysis Script Deduplication and Maintenance

**Multiple versions of similar brute-force algorithms without clear distinction:**
- Files:
  - `485/scripts/bruteforce_7seg.py` (288 lines)
  - `485/scripts/bruteforce_7seg_v2.py` (261 lines)
  - `485/scripts/bruteforce_3digit.py` (289 lines)
- Problem: Scripts are similar enough to be confusing. V2 is shorter but unclear which is "better". The 3-digit variant may have different constraints but that's not clear from naming.
- Fix approach: Document which is the preferred/final version in a README (`485/scripts/README.md`). Consider deleting obsolete versions or archiving to a subfolder.
- Current state: Not blocking anything (all are research), but violates maintainability if this code becomes a reference for future collaborators.

## Phantom Noise During Initial Testing

**Unterminated RS-485 cable caused phantom button presses:**
- Files: `485/rs485-status-2026-03-08.md` (line 65, sensitivity warning)
- Evidence: "Even an unterminated Cat5 breakout cable caused phantom Temp Up presses"
- Current status: Recognized and documented. Mitigated in Phase 2 plan by using isolated photorelays for write (injection) and accepting shared ground for read (display).
- Remaining risk: If Phase 2 is delayed and the prototype sits on breadboard for extended time, someone may accidentally trigger phantom presses again. Not a code issue, but a operational safety note.

---

*Concerns audit: 2026-03-13*
