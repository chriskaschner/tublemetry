#!/usr/bin/env python3
"""Verify MagnusPer/Balboa-GS510SZ approach against VS300FL4 captures.

Uses MagnusPer's exact 7-segment encoding table and clock+data protocol
to decode existing logic analyzer captures (OH.csv, 254.csv).

Success criteria:
  - OH.csv should decode to " OH" / "   " alternating at ~1Hz (flash)
  - 254.csv should decode to a consistent, recognizable display string
  - All frames should have exactly 24 clock pulses
  - All decoded bytes should be in MagnusPer's table (no unknowns)
"""

import csv
import sys
from collections import Counter
from pathlib import Path

# MagnusPer/Balboa-GS510SZ exact encoding table
# Source: Balboa_GS_Interface.cpp
# bit6=a, bit5=b, bit4=c, bit3=d, bit2=e, bit1=f, bit0=g
MAGNUSPER_TABLE = {
    0x7E: "0",
    0x30: "1",
    0x6D: "2",
    0x79: "3",
    0x33: "4",
    0x5B: "5",
    0x5F: "6",
    0x70: "7",
    0x7F: "8",
    0x7B: "9",
    0x00: " ",   # blank
    # Letters from GS510SZ reference
    0x37: "H",
    0x7E: "O",   # same as "0" -- context determines meaning
    0x67: "P",
    0x4F: "E",
    0x0F: "t",
    0x01: "-",
    0x0E: "L",
    0x0D: "c",
    0x05: "r",
    0x1D: "o",
}


def load_channels(path: Path, max_channels: int = 8) -> list[list[int]]:
    """Load logic analyzer channels from CSV."""
    channels: list[list[int]] = [[] for _ in range(max_channels)]
    with open(path) as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            for i in range(min(len(row), max_channels)):
                channels[i].append(int(row[i]))
    return channels


def find_rising_edges(ch: list[int]) -> list[int]:
    return [i for i in range(1, len(ch)) if ch[i - 1] == 0 and ch[i] == 1]


def extract_frames(clock_edges: list[int], gap_threshold: int) -> list[list[int]]:
    """Group clock edges into frames using timing gaps."""
    if not clock_edges:
        return []
    frames = []
    current = [clock_edges[0]]
    for i in range(1, len(clock_edges)):
        gap = clock_edges[i] - clock_edges[i - 1]
        if gap > gap_threshold:
            frames.append(current)
            current = [clock_edges[i]]
        else:
            current.append(clock_edges[i])
    if current:
        frames.append(current)
    return frames


def decode_frame(edges: list[int], data_ch: list[int], n_samples: int,
                 sample_offset: int = 2) -> dict:
    """Decode one frame of 24 bits into 3 digits + 3 status bits."""
    bits = []
    for edge in edges:
        idx = edge + sample_offset
        if idx < n_samples:
            bits.append(data_ch[idx])
        else:
            bits.append(0)

    result = {"bits": bits, "num_bits": len(bits), "digits": [], "values": [],
              "status_bits": [], "display": "", "all_known": True}

    # 3 x 7-bit digits
    for d in range(3):
        start = d * 7
        chunk = bits[start:start + 7]
        if len(chunk) < 7:
            result["digits"].append("?")
            result["values"].append(-1)
            result["all_known"] = False
            continue
        val = 0
        for b in chunk:
            val = (val << 1) | b
        result["values"].append(val)
        char = MAGNUSPER_TABLE.get(val)
        if char is None:
            result["digits"].append(f"?0x{val:02X}")
            result["all_known"] = False
        else:
            result["digits"].append(char)

    # 3 status bits
    result["status_bits"] = bits[21:24]
    result["display"] = "".join(result["digits"])
    return result


def analyze_capture(path: Path, sample_rate: int):
    """Full analysis of a logic analyzer capture."""
    print(f"\n{'=' * 60}")
    print(f"ANALYZING: {path.name}")
    print(f"{'=' * 60}")

    channels = load_channels(path)
    n = len(channels[0])
    duration_ms = n / sample_rate * 1000
    print(f"Samples: {n:,} ({duration_ms:.1f}ms at {sample_rate/1e6:.0f}MHz)")

    # Find active channels
    for i in range(8):
        trans = sum(1 for j in range(1, n) if channels[i][j] != channels[i][j - 1])
        if trans > 0:
            print(f"  CH{i}: {trans} transitions")

    # CH5 = clock (Pin 6), CH4 = data (Pin 5)
    clock_ch = channels[5]
    data_ch = channels[4]

    rising = find_rising_edges(clock_ch)
    print(f"\nClock rising edges: {len(rising)}")

    # Frame extraction (gap > 500us = new frame)
    gap_threshold = int(sample_rate * 0.0005)  # 500us in samples
    frames = extract_frames(rising, gap_threshold)

    pulse_counts = Counter(len(f) for f in frames)
    print(f"Frames: {len(frames)}")
    print(f"Pulses per frame: {dict(pulse_counts)}")

    if pulse_counts.get(24, 0) != len(frames):
        print("!! WARNING: Not all frames have 24 pulses!")

    # Frame timing
    if len(frames) >= 2:
        intervals = []
        for i in range(1, len(frames)):
            gap_samples = frames[i][0] - frames[i - 1][0]
            intervals.append(gap_samples / sample_rate * 1000)
        avg_interval = sum(intervals) / len(intervals)
        freq = 1000 / avg_interval if avg_interval > 0 else 0
        print(f"Frame interval: {avg_interval:.1f}ms avg ({freq:.1f}Hz)")

    # Decode all frames
    display_counts: Counter = Counter()
    unknown_bytes: list[int] = []
    all_results = []

    for fi, frame_edges in enumerate(frames):
        if len(frame_edges) != 24:
            continue
        result = decode_frame(frame_edges, data_ch, n)
        all_results.append(result)
        display_counts[result["display"]] += 1
        if not result["all_known"]:
            for v in result["values"]:
                if v not in MAGNUSPER_TABLE:
                    unknown_bytes.append(v)

    print(f"\nDecoded {len(all_results)} frames:")
    for display, count in display_counts.most_common():
        pct = count / len(all_results) * 100
        hex_str = ""
        # Find a frame with this display to show hex values
        for r in all_results:
            if r["display"] == display:
                hex_str = " ".join(f"0x{v:02X}" for v in r["values"])
                status = "".join(str(b) for b in r["status_bits"])
                break
        print(f"  \"{display}\" x{count} ({pct:.0f}%) -- bytes: {hex_str}, status: {status}")

    if unknown_bytes:
        print(f"\n!! UNKNOWN BYTES (not in MagnusPer table):")
        for val in sorted(set(unknown_bytes)):
            print(f"  0x{val:02X} = {val:07b}b ({unknown_bytes.count(val)} occurrences)")
    else:
        print(f"\nAll bytes decoded successfully using MagnusPer table.")

    # Check for flash pattern (OH.csv should alternate)
    if len(all_results) > 10:
        transitions = sum(
            1 for i in range(1, len(all_results))
            if all_results[i]["display"] != all_results[i - 1]["display"]
        )
        if transitions > 0:
            # Find flash timing
            flash_points = [
                i for i in range(1, len(all_results))
                if all_results[i]["display"] != all_results[i - 1]["display"]
            ]
            if len(flash_points) >= 2 and len(frames) > flash_points[1]:
                gap_between_flashes = (
                    (frames[flash_points[1]][0] - frames[flash_points[0]][0])
                    / sample_rate * 1000
                )
                print(f"\nFlash pattern detected: {transitions} transitions")
                print(f"  Flash interval: ~{gap_between_flashes:.0f}ms")
                # Show first few transitions
                for fp in flash_points[:6]:
                    time_ms = frames[fp][0] / sample_rate * 1000
                    prev = all_results[fp - 1]["display"]
                    curr = all_results[fp]["display"]
                    print(f"  @{time_ms:.0f}ms: \"{prev}\" -> \"{curr}\"")

    return display_counts, unknown_bytes


def main():
    base = Path(__file__).parent.parent

    # OH.csv: 1MHz sample rate, OH error display flashing
    oh_path = base / "OH.csv"
    if oh_path.exists():
        oh_displays, oh_unknowns = analyze_capture(oh_path, sample_rate=1_000_000)

        print(f"\n--- OH.csv VERDICT ---")
        expected = {" OH", "   "}
        actual = set(oh_displays.keys())
        if actual == expected and not oh_unknowns:
            print("PASS: Decodes to \" OH\" / \"   \" flash with zero unknowns")
        elif actual.issubset(expected) and not oh_unknowns:
            print(f"PASS (partial): Only saw {actual}, no unknowns")
        else:
            print(f"MIXED: Got {actual}, unknowns: {len(oh_unknowns)}")

    # 254.csv: 4MHz sample rate, idle tub
    csv254_path = base / "254.csv"
    if csv254_path.exists():
        csv254_displays, csv254_unknowns = analyze_capture(csv254_path, sample_rate=4_000_000)

        print(f"\n--- 254.csv VERDICT ---")
        actual = set(csv254_displays.keys())
        if not csv254_unknowns:
            print(f"PASS: All bytes in MagnusPer table. Display: {actual}")
        else:
            print(f"MIXED: Got {actual}, unknowns: {len(csv254_unknowns)}")

    # Overall verdict
    print(f"\n{'=' * 60}")
    print("MAGNUSPER COMPATIBILITY VERDICT")
    print(f"{'=' * 60}")
    all_unknowns = (oh_unknowns if oh_path.exists() else []) + \
                   (csv254_unknowns if csv254_path.exists() else [])
    if not all_unknowns:
        print("CONFIRMED: MagnusPer's clock+data approach and 7-segment table")
        print("work for VS300FL4. Same protocol, same encoding.")
        print("")
        print("Differences from GS510SZ:")
        print("  - 24 bits/frame (not 39)")
        print("  - 3 digits (not 4+status)")
        print("  - Buttons on analog pins (not in clock cycle)")
    else:
        unknown_set = sorted(set(all_unknowns))
        print(f"PARTIAL: {len(unknown_set)} byte value(s) not in MagnusPer table:")
        for v in unknown_set:
            print(f"  0x{v:02X}")


if __name__ == "__main__":
    main()
