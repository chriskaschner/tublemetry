"""Tests for the firmware frame decoder (frame_decode.h).

These compile the REAL C++ header on the host (tests/firmware/
frame_decode_harness.cpp), like test_water_temp_gate.py, so what passes here is
what ships to the ESP32.

WHY THIS EXISTS (2026-11-06): the heater flag is p1 bit 2, and p1 is the FIRST
DIGIT byte. The checksum forbids p1 bits 6,3,1,0, so digit 1 can only use
segments b, c and e -- i.e. it is blank or "1", and segment e is never a real
segment there: it is the heater flag. The old decoder looked the whole byte up
in SEVEN_SEG_TABLE. "1" + heater (0x34) happened to be in the table, but
blank + heater (0x04) is not, so with the heater on and the water at 99F or
below, every frame decoded as "?", was dropped as partial, and returned BEFORE
the status bits were read. Display, water temperature, heater and pump all froze
in HA for the whole sub-100F part of every heat-up.

Seen live on 2026-11-06: water read 98 at 06:51, then nothing until heater-on
and 100 arrived together at 07:08 (no 99 ever published); 10-28 held 94 for
54 min while heating.

The frames are built from the confirmed segment bytes, not from the bit strings
in protocol/examples/README.md: those do not split into the [7][7][7][3] layout
(its "105" string splits to 0x30 0x7E 0x33, which is "104"), so they are not
trustworthy test input.

Frame layout (MSB first): [digit1:7][digit2:7][digit3:7][status:3]
status bit 2 = pump, bit 1 = light, bit 0 must be 0.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "esphome" / "components" / "tublemetry_display"
HARNESS = Path(__file__).resolve().parent / "firmware" / "frame_decode_harness.cpp"

CXX = shutil.which("clang++") or shutil.which("g++")
pytestmark = pytest.mark.skipif(CXX is None, reason="no host C++ compiler")

# Segment bytes
BLANK, ONE, ONE_HEATER, BLANK_HEATER = 0x00, 0x30, 0x34, 0x04
D = {"0": 0x7E, "1": 0x30, "2": 0x6D, "3": 0x79, "4": 0x33, "5": 0x5B,
     "6": 0x5F, "7": 0x70, "8": 0x7F, "9": 0x73, "E": 0x4F, "c": 0x0D, "L": 0x0E, "t": 0x0F}
PUMP, LIGHT = 0b100, 0b010


def frame(d1: int, d2: int, d3: int, status: int = 0) -> int:
    return (d1 << 17) | (d2 << 10) | (d3 << 3) | status


@pytest.fixture(scope="module")
def decoder(tmp_path_factory):
    out = tmp_path_factory.mktemp("frame") / "frame_decode"
    subprocess.run(
        [CXX, "-std=c++17", "-Wall", "-Wextra", "-Werror", f"-I{COMPONENT}",
         str(HARNESS), "-o", str(out)],
        check=True,
        capture_output=True,
    )

    def run(*frames: int) -> list[dict]:
        stdin = "".join(f"{f:#08x}\n" for f in frames)
        res = subprocess.run([str(out)], input=stdin, capture_output=True, text=True, check=True)
        rows = []
        for line in res.stdout.splitlines():
            chars, ok, known, heater, pump, light = line.split("|")
            rows.append({"chars": chars, "checksum_ok": ok == "1", "known": int(known),
                         "heater": heater == "1", "pump": pump == "1", "light": light == "1"})
        return rows

    return run


# --- the bug: blank first digit with the heater on ---------------------------


def test_sub_100_reading_with_heater_on_decodes(decoder):
    (f,) = decoder(frame(BLANK_HEATER, D["9"], D["8"]))
    assert f["chars"] == " 98"
    assert f["known"] == 3, "frame must not be dropped as partial"
    assert f["heater"] is True


def test_sub_100_reading_with_heater_and_pump_on(decoder):
    (f,) = decoder(frame(BLANK_HEATER, D["9"], D["9"], PUMP))
    assert f["chars"] == " 99"
    assert (f["known"], f["heater"], f["pump"]) == (3, True, True)


def test_economy_display_with_heater_on_decodes(decoder):
    (f,) = decoder(frame(BLANK_HEATER, D["E"], D["c"], PUMP))
    assert f["chars"] == " Ec"
    assert (f["known"], f["heater"], f["pump"]) == (3, True, True)


def test_blank_display_with_heater_on_decodes(decoder):
    (f,) = decoder(frame(BLANK_HEATER, BLANK, BLANK))
    assert f["chars"] == "   "
    assert (f["known"], f["heater"]) == (3, True)


# --- behaviour that must not change ------------------------------------------


def test_100_plus_with_heater_on_still_reads_one(decoder):
    (f,) = decoder(frame(ONE_HEATER, D["0"], D["5"]))
    assert f["chars"] == "105"
    assert (f["known"], f["heater"]) == (3, True)


def test_100_plus_heater_off(decoder):
    (f,) = decoder(frame(ONE, D["0"], D["4"]))
    assert f["chars"] == "104"
    assert (f["known"], f["heater"]) == (3, False)


def test_sub_100_heater_off(decoder):
    (f,) = decoder(frame(BLANK, D["9"], D["0"]))
    assert f["chars"] == " 90"
    assert (f["known"], f["heater"]) == (3, False)


def test_economy_display_heater_off(decoder):
    (f,) = decoder(frame(BLANK, D["E"], D["c"], PUMP))
    assert f["chars"] == " Ec"
    assert f["checksum_ok"] and f["pump"] and not f["heater"]


def test_status_bits(decoder):
    rows = decoder(frame(ONE, D["0"], D["4"], PUMP), frame(ONE, D["0"], D["4"], LIGHT))
    assert (rows[0]["pump"], rows[0]["light"]) == (True, False)
    assert (rows[1]["pump"], rows[1]["light"]) == (False, True)


def test_heater_mask_applies_to_first_digit_only(decoder):
    # 0x04 is not a valid glyph in positions 2 and 3; it must still be unknown.
    (f,) = decoder(frame(ONE, BLANK_HEATER, D["4"]))
    assert f["chars"][1] == "?"
    assert f["known"] == 2


@pytest.mark.parametrize("bad_p1", [0x40, 0x08, 0x02, 0x01])
def test_checksum_rejects_forbidden_p1_bits(decoder, bad_p1):
    (f,) = decoder(frame(ONE | bad_p1, D["0"], D["4"]))
    assert f["checksum_ok"] is False


def test_checksum_rejects_status_bit0(decoder):
    (f,) = decoder(frame(ONE, D["0"], D["4"], 0b001))
    assert f["checksum_ok"] is False


def test_checksum_accepts_heater_bit(decoder):
    (f,) = decoder(frame(BLANK_HEATER, D["9"], D["8"]))
    assert f["checksum_ok"] is True
