#!/usr/bin/env python3
"""Deeper analysis of 254.csv as synchronous clock+data.

Look at raw waveforms around clock edges to understand the protocol.
"""

import csv
import sys
from pathlib import Path

SAMPLE_RATE = 4_000_000
CSV_PATH = Path(__file__).parent.parent / "254.csv"

SEG_TABLE = {
    0x7E: "0", 0x30: "1", 0x6D: "2", 0x79: "3", 0x33: "4",
    0x5B: "5", 0x5F: "6", 0x70: "7", 0x7F: "8", 0x73: "9",
    0x00: " ", 0x37: "H", 0x0E: "L", 0x4F: "E", 0x0D: "c", 0x0F: "t",
}


def load_channels(path: Path) -> list[list[int]]:
    """Load channels from CSV (supports sigrok comment headers and variable channel count)."""
    channels: list[list[int]] | None = None
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            parts = line.split(",")
            # Skip non-numeric header rows (e.g. "logic,logic")
            try:
                vals = [int(v) for v in parts]
            except ValueError:
                continue
            if channels is None:
                channels = [[] for _ in range(len(vals))]
            for i, v in enumerate(vals):
                channels[i].append(v)
    if channels is None:
        channels = [[] for _ in range(8)]
    # Pad to 8 channels for compatibility with code that indexes by channel number
    while len(channels) < 8:
        channels.append([0] * len(channels[0]) if channels[0] else [])
    return channels


def find_rising(ch: list[int]) -> list[int]:
    return [i for i in range(1, len(ch)) if ch[i - 1] == 0 and ch[i] == 1]


def find_falling(ch: list[int]) -> list[int]:
    return [i for i in range(1, len(ch)) if ch[i - 1] == 1 and ch[i] == 0]


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else CSV_PATH
    print(f"Loading {path}...")
    channels = load_channels(path)
    n = len(channels[0])
    print(f"Loaded {n} samples ({n / SAMPLE_RATE * 1000:.1f}ms)")

    # Survey active channels
    num_ch = sum(1 for ch in channels if ch and any(v != 0 for v in ch[:100]))
    print(f"\nChannel activity ({num_ch} active):")
    for i in range(min(len(channels), 8)):
        if not channels[i]:
            continue
        trans = sum(1 for j in range(1, n) if channels[i][j] != channels[i][j - 1])
        idle = channels[i][0]
        print(f"  CH{i}: {trans} transitions, idle={idle}")

    # Auto-detect channel layout:
    # 2-channel capture: D0=data (Pin 5), D1=clock (Pin 6)
    # 8-channel capture: CH4=data (Pin 5), CH5=clock (Pin 6)
    if num_ch <= 2:
        data_ch = channels[0]  # D0 = Pin 5 data
        clk_ch = channels[1]   # D1 = Pin 6 clock
        print("\n2-channel mode: D0=data, D1=clock")
    else:
        data_ch = channels[4]  # CH4 = Pin 5 data
        clk_ch = channels[5]   # CH5 = Pin 6 clock
        print("\n8-channel mode: CH4=data, CH5=clock")

    clk_rising = find_rising(clk_ch)
    clk_falling = find_falling(clk_ch)
    print(f"\nClock rising edges: {len(clk_rising)}")
    print(f"Clock falling edges: {len(clk_falling)}")

    # Show gaps between rising edges to understand frame boundaries
    gaps = [(clk_rising[i] - clk_rising[i - 1]) for i in range(1, len(clk_rising))]
    large_gaps = [(i, g) for i, g in enumerate(gaps) if g > 2000]  # > 500us
    print(f"Large gaps (>500us): {len(large_gaps)}")
    if large_gaps:
        print(f"  First few: {[(i, f'{g/4:.0f}us') for i, g in large_gaps[:5]]}")

    # Group clock edges into frames using large gap as boundary
    threshold = 2000  # 500us
    frames = []
    current = [clk_rising[0]]
    for i in range(1, len(clk_rising)):
        gap = clk_rising[i] - clk_rising[i - 1]
        if gap > threshold:
            frames.append(current)
            current = [clk_rising[i]]
        else:
            current.append(clk_rising[i])
    if current:
        frames.append(current)

    print(f"\nFrames: {len(frames)}")
    print(f"Pulses per frame: {sorted(set(len(f) for f in frames))}")

    # Decode ALL frames at offset 0 and show unique values with counts
    print(f"\n{'=' * 60}")
    print("All unique decoded values (offset +0, MSB-first)")
    print(f"{'=' * 60}")
    from collections import Counter
    decoded_frames = []
    for fi, frame_edges in enumerate(frames):
        bits = []
        for edge in frame_edges:
            if edge < n:
                bits.append(data_ch[edge])
        display = ""
        for cs in range(0, min(len(bits), 28), 7):
            chunk = bits[cs:cs + 7]
            if len(chunk) == 7:
                val = 0
                for b in chunk:
                    val = (val << 1) | b
                display += SEG_TABLE.get(val, f"?0x{val:02X}")
        decoded_frames.append((fi, display))
    counts = Counter(d for _, d in decoded_frames)
    for display, count in counts.most_common():
        first_frame = next(fi for fi, d in decoded_frames if d == display)
        time_s = frames[first_frame][0] / SAMPLE_RATE
        print(f"  \"{display}\" x{count} frames (first at frame {first_frame}, {time_s:.3f}s)")

    # For each frame, sample data at different offsets from rising edge
    print(f"\n{'=' * 60}")
    print("Sampling data at various offsets from clock rising edge")
    print(f"{'=' * 60}")

    for offset_samples in [0, 2, 5, 10, 20, 50]:
        offset_us = offset_samples / 4
        print(f"\n--- Offset: +{offset_samples} samples ({offset_us:.1f}us) ---")
        for fi in range(min(3, len(frames))):
            bits = []
            for edge in frames[fi]:
                idx = edge + offset_samples
                if idx < n:
                    bits.append(data_ch[idx])
            bit_str = "".join(str(b) for b in bits)

            # Try decoding as 7-seg chunks
            display = ""
            for cs in range(0, min(len(bits), 28), 7):
                chunk = bits[cs:cs + 7]
                if len(chunk) == 7:
                    val = 0
                    for b in chunk:
                        val = (val << 1) | b
                    char = SEG_TABLE.get(val, f"?0x{val:02X}")
                    display += char

            # Also try reversed bit order within chunks
            display_rev = ""
            for cs in range(0, min(len(bits), 28), 7):
                chunk = bits[cs:cs + 7]
                if len(chunk) == 7:
                    val = 0
                    for b in reversed(chunk):
                        val = (val << 1) | b
                    char = SEG_TABLE.get(val, f"?0x{val:02X}")
                    display_rev += char

            print(f"  Frame {fi} ({len(bits)} bits): {bit_str}")
            print(f"    MSB-first: {display}")
            print(f"    LSB-first: {display_rev}")

    # Also try sampling on FALLING edge of clock
    print(f"\n{'=' * 60}")
    print("Sampling data on FALLING clock edge")
    print(f"{'=' * 60}")

    fall_frames = []
    current = [clk_falling[0]]
    for i in range(1, len(clk_falling)):
        gap = clk_falling[i] - clk_falling[i - 1]
        if gap > threshold:
            fall_frames.append(current)
            current = [clk_falling[i]]
        else:
            current.append(clk_falling[i])
    if current:
        fall_frames.append(current)

    print(f"Frames: {len(fall_frames)}, pulses/frame: {sorted(set(len(f) for f in fall_frames))}")
    for fi in range(min(3, len(fall_frames))):
        bits = [data_ch[e] if e < n else 0 for e in fall_frames[fi]]
        bit_str = "".join(str(b) for b in bits)
        display = ""
        display_rev = ""
        for cs in range(0, min(len(bits), 28), 7):
            chunk = bits[cs:cs + 7]
            if len(chunk) == 7:
                val_msb = 0
                val_lsb = 0
                for b in chunk:
                    val_msb = (val_msb << 1) | b
                for b in reversed(chunk):
                    val_lsb = (val_lsb << 1) | b
                display += SEG_TABLE.get(val_msb, f"?0x{val_msb:02X}")
                display_rev += SEG_TABLE.get(val_lsb, f"?0x{val_lsb:02X}")
        print(f"  Frame {fi} ({len(bits)} bits): {bit_str}")
        print(f"    MSB-first: {display}")
        print(f"    LSB-first: {display_rev}")

    # Show raw waveform around first few clock edges
    print(f"\n{'=' * 60}")
    print("Raw waveform around first 5 clock rising edges")
    print(f"{'=' * 60}")
    for ei in range(min(5, len(clk_rising))):
        edge = clk_rising[ei]
        window = 20  # samples before and after
        start = max(0, edge - window)
        end = min(n, edge + window)
        clk_vals = clk_ch[start:end]
        dat_vals = data_ch[start:end]
        print(f"\nEdge {ei} at sample {edge} ({edge/4:.1f}us):")
        print(f"  CLK: {''.join(str(v) for v in clk_vals)}")
        print(f"  DAT: {''.join(str(v) for v in dat_vals)}")
        print(f"       {''.join('^' if i == window else ' ' for i in range(len(clk_vals)))}")


if __name__ == "__main__":
    main()
