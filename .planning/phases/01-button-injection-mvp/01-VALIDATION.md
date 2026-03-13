---
phase: 1
slug: button-injection-mvp
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-13
---

# Phase 1 -- Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (Python, managed via uv) |
| **Config file** | none -- Wave 0 creates pyproject.toml with pytest config |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 0 | DISP-01 | unit | `uv run pytest tests/test_decode.py -x` | -- W0 | pending |
| 01-01-02 | 01 | 0 | DISP-01 | unit | `uv run pytest tests/test_frame_parser.py -x` | -- W0 | pending |
| 01-01-03 | 01 | 0 | DISP-01 | unit | `uv run pytest tests/test_display_state.py -x` | -- W0 | pending |
| 01-02-01 | 02 | 1 | DISP-01 | unit | `uv run pytest tests/test_decode.py::test_7seg_lookup -x` | -- W0 | pending |
| 01-02-02 | 02 | 1 | DISP-01 | unit | `uv run pytest tests/test_frame_parser.py::test_idle_frame -x` | -- W0 | pending |
| 01-02-03 | 02 | 1 | DISP-01 | unit | `uv run pytest tests/test_display_state.py::test_non_temp_states -x` | -- W0 | pending |
| 01-02-04 | 02 | 1 | DISP-01 | unit | `uv run pytest tests/test_display_state.py::test_temp_persistence -x` | -- W0 | pending |
| 01-03-01 | 03 | 2 | DISP-02 | integration | Manual -- flash ESP32, verify HA entity | N/A | pending |
| 01-03-02 | 03 | 2 | DISP-02 | integration | Manual -- verify diagnostic sensors | N/A | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `pyproject.toml` -- project config with pytest dependency
- [ ] `tests/conftest.py` -- shared fixtures (sample frames, expected decode results)
- [ ] `tests/test_decode.py` -- 7-segment lookup table tests (parameterized by ladder capture data)
- [ ] `tests/test_frame_parser.py` -- frame parsing tests with known byte sequences
- [ ] `tests/test_display_state.py` -- display state machine tests (temperature persistence, edge states)
- [ ] Framework install: `uv add --dev pytest`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Climate entity reports correct temperature | DISP-02 | Requires physical ESP32 + hot tub | Flash firmware, verify HA entity shows correct temp vs tub display |
| Diagnostic sensors populate in HA | DISP-02 | Requires physical ESP32 + HA instance | Verify entity_category: diagnostic sensors appear in HA |

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
