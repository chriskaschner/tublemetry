# T03: 01-button-injection-mvp 03

**Slice:** S01 — **Milestone:** M001

## Description

Close verification gaps from 01-VERIFICATION.md: fix premature requirement status, add structural YAML test to prevent indentation-as-nesting regressions, and prepare temperature ladder capture tooling so everything is ready when hardware arrives.

Purpose: The verification found REQUIREMENTS.md prematurely marks DISP-01/DISP-02 as complete, the existing YAML tests miss structural issues (key nesting), and no structured capture tooling exists for the critical ladder capture session. These are all code-actionable fixes that do not require hardware.

Output: Updated REQUIREMENTS.md, enhanced YAML tests, tested ladder capture script.

## Must-Haves

- [ ] "REQUIREMENTS.md reflects actual state: DISP-01 and DISP-02 show hardware verification pending, not prematurely complete"
- [ ] "A structural YAML test catches top-level keys accidentally nested under other keys (indentation-as-nesting)"
- [ ] "A temperature ladder capture script exists and is tested, ready to run when hardware arrives"

## Files

- `.planning/REQUIREMENTS.md`
- `tests/test_esphome_yaml.py`
- `485/scripts/ladder_capture.py`
- `tests/test_ladder_capture.py`
