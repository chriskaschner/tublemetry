"""Tests for the firmware water-temperature gate (water_temp_gate.h).

These compile the REAL C++ header on the host (tests/firmware/
water_temp_gate_harness.cpp) instead of testing a Python mirror of it, so what
passes here is what ships to the ESP32.

WHY THE GATE EXISTS (2026-09-27): sensor.tublemetry_hot_tub_temperature had two
defects.

1. `delta: 1.0` in esphome/tublemetry.yaml is strictly-greater in ESPHome
   (DeltaFilter: `delta > min`), and the panel shows whole degrees, so every
   real 1F step was discarded.
2. A setpoint flash starts with a value frame BEFORE the first blank, while
   in_set_mode_ is still false, so that frame was published as water
   temperature. Every later frame was suppressed while set mode lasted, so the
   heartbeat filter kept re-sending the leaked value. HA recorded 90.0 at
   2026-09-27 10:00:01 and 80.0 at 2026-09-26 02:21:32 that way.

The gate publishes a value only after the panel has shown it continuously for
STABLE_MS with no interrupting frame. Setpoint flashes alternate with blanks
roughly every 0.5 s, so they can never qualify; real water temperature holds for
minutes.

The two REPLAY timelines below are the display-string changes HA recorded
(sensor.tublemetry_hot_tub_display, millisecond timestamps) around those two
leaks, re-expanded into frames at the panel's ~60 Hz.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "esphome" / "components" / "tublemetry_display"
HARNESS = Path(__file__).resolve().parent / "firmware" / "water_temp_gate_harness.cpp"

FRAME_MS = 16  # ~60 Hz
STABLE_MS = 3000

CXX = shutil.which("clang++") or shutil.which("g++")
pytestmark = pytest.mark.skipif(CXX is None, reason="no host C++ compiler")


@pytest.fixture(scope="module")
def gate_bin(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("gate") / "water_temp_gate"
    subprocess.run(
        [CXX, "-std=c++17", "-Wall", "-Wextra", "-Werror", f"-I{COMPONENT}",
         str(HARNESS), "-o", str(out)],
        check=True,
        capture_output=True,
    )
    return out


def frames(changes: list[tuple[float, str]], end_s: float, t0_ms: int = 0) -> list[tuple[int, str]]:
    """Expand (seconds, display) change points into one frame every FRAME_MS.

    Each display value is held until the next change point, which is how the
    panel behaves: it repeats the current frame continuously.
    """
    out = []
    changes = sorted(changes)
    t = changes[0][0]
    i = 0
    while t < end_s:
        while i + 1 < len(changes) and changes[i + 1][0] <= t:
            i += 1
        out.append(((t0_ms + round(t * 1000)) & 0xFFFFFFFF, changes[i][1]))
        t += FRAME_MS / 1000
    return out


def run(gate_bin: Path, frame_list: list[tuple[int, str]]) -> list[tuple[int, float]]:
    stdin = "".join(f"{ms} {disp}\n" for ms, disp in frame_list)
    res = subprocess.run([str(gate_bin)], input=stdin, capture_output=True, text=True, check=True)
    pubs = []
    for line in res.stdout.splitlines():
        _, ms, val = line.split()
        pubs.append((int(ms), float(val)))
    return pubs


BLANK = "   "

# 2026-09-27 10:00 UTC. Injection 102 -> 104 while the water sat at 100.
# Seconds relative to 10:00:00.000. HA published 90.0 (the leading frame).
REPLAY_0927 = [
    (-10.0, "100"),
    (0.986, " 90"), (1.416, BLANK), (1.929, " 92"), (2.421, BLANK),
    (2.928, " 93"), (3.030, " 94"), (3.422, BLANK), (3.928, " 95"),
    (4.076, " 96"), (4.430, BLANK), (4.913, " 97"), (5.112, " 98"),
    (5.426, BLANK), (5.932, " 99"), (6.170, "100"), (6.429, BLANK),
    (6.931, "101"), (7.208, "102"), (7.427, BLANK), (7.837, "103"),
    (8.423, BLANK), (8.914, "104"), (9.419, BLANK), (9.938, "104"),
    (10.439, BLANK), (10.928, "104"), (11.431, BLANK), (11.934, "104"),
    (12.436, BLANK), (12.940, "100"),
]

# 2026-09-26 02:21 UTC. Down-move to 80 that failed verification and retried,
# water at 105 throughout. HA published 80.0 (the retry's leading frame).
REPLAY_0926 = [
    (-20.0, "105"),
    (0.487, " 89"), (0.913, BLANK), (1.498, " 87"), (1.942, BLANK),
    (2.497, " 85"), (3.012, BLANK), (3.509, " 83"), (4.004, BLANK),
    (4.477, " 81"), (4.983, BLANK), (5.487, " 80"), (5.979, BLANK),
    (6.498, " 80"), (6.989, BLANK), (7.499, " 80"), (8.005, BLANK),
    (8.491, " 80"), (8.998, BLANK), (9.487, " 80"), (9.993, BLANK),
    (10.496, " 80"), (11.001, BLANK), (11.244, "105"),
    (32.656, " 80"), (32.997, BLANK), (33.503, " 81"), (33.996, BLANK),
    (34.516, " 83"), (35.011, BLANK), (35.480, " 85"), (36.004, BLANK),
    (36.485, " 87"), (36.995, BLANK), (37.503, " 89"), (38.017, BLANK),
    (38.502, " 90"), (39.004, BLANK), (39.502, " 90"), (40.009, BLANK),
    (40.491, " 90"), (41.004, BLANK), (41.500, " 90"), (42.007, BLANK),
    (42.233, "105"),
]


class TestRecordedLeaks:
    """The two leaks HA actually recorded must not reproduce."""

    def test_0927_injection_publishes_only_the_water_temperature(self, gate_bin):
        pubs = run(gate_bin, frames(REPLAY_0927, end_s=60.0, t0_ms=100_000))
        assert [v for _, v in pubs] == [100.0], pubs

    def test_0927_leading_flash_frame_is_not_published(self, gate_bin):
        pubs = run(gate_bin, frames(REPLAY_0927, end_s=60.0, t0_ms=100_000))
        assert 90.0 not in [v for _, v in pubs]

    def test_0926_retry_publishes_only_the_water_temperature(self, gate_bin):
        pubs = run(gate_bin, frames(REPLAY_0926, end_s=80.0, t0_ms=100_000))
        assert [v for _, v in pubs] == [105.0], pubs

    def test_no_setpoint_flash_value_ever_escapes(self, gate_bin):
        flashes = {80.0, 81.0, 83.0, 85.0, 87.0, 89.0, 90.0, 92.0, 93.0, 94.0,
                   95.0, 96.0, 97.0, 98.0, 99.0, 101.0, 102.0, 103.0, 104.0}
        for replay, end in ((REPLAY_0927, 60.0), (REPLAY_0926, 80.0)):
            pubs = run(gate_bin, frames(replay, end_s=end, t0_ms=100_000))
            assert not flashes & {v for _, v in pubs}, pubs


class TestOneDegreeSteps:
    """The delta-filter bug: real 1F changes must reach HA."""

    def test_one_degree_drop_is_published(self, gate_bin):
        pubs = run(gate_bin, frames([(0, "103"), (60, "102")], end_s=90))
        assert [v for _, v in pubs] == [103.0, 102.0]

    def test_one_degree_rise_is_published(self, gate_bin):
        pubs = run(gate_bin, frames([(0, "101"), (60, "102"), (120, "103")], end_s=150))
        assert [v for _, v in pubs] == [101.0, 102.0, 103.0]

    def test_step_is_published_after_the_stability_window(self, gate_bin):
        pubs = run(gate_bin, frames([(0, "103"), (60, "102")], end_s=90))
        step_ms = pubs[1][0] - 60_000
        assert STABLE_MS <= step_ms < STABLE_MS + 2 * FRAME_MS


class TestStabilityWindow:
    def test_first_value_after_boot_waits_for_the_window(self, gate_bin):
        pubs = run(gate_bin, frames([(0, "100")], end_s=10))
        assert len(pubs) == 1
        assert STABLE_MS <= pubs[0][0] < STABLE_MS + 2 * FRAME_MS

    def test_value_shorter_than_window_is_never_published(self, gate_bin):
        # 2.9 s on, 0.5 s blank, repeated: slower than any real flash, still blocked.
        changes = []
        for k in range(10):
            changes += [(k * 3.4, "95"), (k * 3.4 + 2.9, BLANK)]
        assert run(gate_bin, frames(changes, end_s=34)) == []

    def test_unchanged_value_is_published_once(self, gate_bin):
        pubs = run(gate_bin, frames([(0, "100")], end_s=120))
        assert [v for _, v in pubs] == [100.0]

    def test_same_value_after_interruption_is_not_republished(self, gate_bin):
        pubs = run(gate_bin, frames([(0, "100"), (20, "Ec"), (25, "100")], end_s=60))
        assert [v for _, v in pubs] == [100.0]

    def test_different_value_after_non_numeric_state_is_published(self, gate_bin):
        pubs = run(gate_bin, frames([(0, "100"), (20, "Ec"), (25, "99")], end_s=60))
        assert [v for _, v in pubs] == [100.0, 99.0]

    def test_millis_wraparound(self, gate_bin):
        # millis() wraps every ~49.7 days; the window must still be measured correctly.
        t0 = 0xFFFFFFFF - 1500
        pubs = run(gate_bin, frames([(0, "100"), (30, "101")], end_s=60, t0_ms=t0))
        assert [v for _, v in pubs] == [100.0, 101.0]
