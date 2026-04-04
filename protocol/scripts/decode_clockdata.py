#!/usr/bin/env python3
"""Decode 254.csv as synchronous clock+data protocol (MagnusPer approach).

CH4 = Pin 5 (display data or clock)
CH5 = Pin 6 (clock or display data)
Sample rate: 4MHz (0.25us per sample)

MagnusPer GS510SZ protocol:
  - Pin 6 = Clock, Pin 5 = Data
  - Clock pulses 7 times per chunk, 39 display bits + 3 button bits = 42 total
  - Frame boundary: gap > threshold between clock pulses
  - Data sampled on clock rising edge
  - 7-segment: bits 0-6 = digit 1, bits 7-13 = digit 2, etc.
"""

import csv
import sys
from pathlib import Path

SAMPLE_RATE = 4_000_000  # 4MHz
CSV_PATH = Path(__file__).parent.parent / "254.csv"

# GS510SZ 7-segment lookup (same as our decode.py)
SEG_TABLE = {
    0b1111110: "0",  # 0x7E
    0b0110000: "1",  # 0x30
    0b1101101: "2",  # 0x6D
    0b1111001: "3",  # 0x79
    0b0110011: "4",  # 0x33
    0b1011011: "5",  # 0x5B
    0b1011111: "6",  # 0x5F
    0b1110000: "7",  # 0x70
    0b1111111: "8",  # 0x7F
    0b1111011: "9",  # 0x7B
    0b0000000: " ",  # blank
}


def load_channels(path: Path) -> tuple[list[int], list[int]]:
    """Load CH4 and CH5 from CSV."""
    ch4 = []
    ch5 = []
    with open(path) as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            ch4.append(int(row[4]))
            ch5.append(int(row[5]))
    return ch4, ch5


def find_edges(channel: list[int], edge: str = "rising") -> list[int]:
    """Find sample indices of rising or falling edges."""
    edges = []
    for i in range(1, len(channel)):
        if edge == "rising" and channel[i - 1] == 0 and channel[i] == 1:
            edges.append(i)
        elif edge == "falling" and channel[i - 1] == 1 and channel[i] == 0:
            edges.append(i)
    return edges


def find_frames(clock_edges: list[int], gap_samples: int) -> list[list[int]]:
    """Group clock edges into frames based on gap threshold."""
    if not clock_edges:
        return []
    frames = []
    current_frame = [clock_edges[0]]
    for i in range(1, len(clock_edges)):
        gap = clock_edges[i] - clock_edges[i - 1]
        if gap > gap_samples:
            frames.append(current_frame)
            current_frame = [clock_edges[i]]
        else:
            current_frame.append(clock_edges[i])
    if current_frame:
        frames.append(current_frame)
    return frames


def decode_display(bits: list[int]) -> str:
    """Decode display bits into characters using 7-segment table."""
    chars = []
    for chunk_start in range(0, min(len(bits), 28), 7):
        chunk = bits[chunk_start:chunk_start + 7]
        if len(chunk) < 7:
            break
        val = 0
        for bit in chunk:
            val = (val << 1) | bit
        char = SEG_TABLE.get(val, f"?{val:07b}")
        chars.append(char)
    return "".join(chars)


def analyze_clock_data(clock: list[int], data: list[int], label: str):
    """Try one channel as clock, other as data."""
    print(f"\n{'=' * 60}")
    print(f"Trying: {label}")
    print(f"{'=' * 60}")

    # Find rising edges on clock channel
    rising = find_edges(clock, "rising")
    falling = find_edges(clock, "falling")
    print(f"Rising edges: {len(rising)}")
    print(f"Falling edges: {len(falling)}")

    if len(rising) < 10:
        print("Too few edges, skipping")
        return

    # Analyze edge timing
    gaps = [rising[i] - rising[i - 1] for i in range(1, len(rising))]
    if gaps:
        min_gap = min(gaps)
        max_gap = max(gaps)
        avg_gap = sum(gaps) / len(gaps)
        print(f"Edge gaps: min={min_gap} ({min_gap/4:.1f}us), "
              f"max={max_gap} ({max_gap/4:.1f}us), "
              f"avg={avg_gap/4:.1f}us")

    # Find frame boundaries (gap > 10x average)
    # MagnusPer uses gap > threshold to detect new cycle
    # Try multiple thresholds
    for threshold_mult in [5, 10, 20, 50]:
        threshold = int(avg_gap * threshold_mult)
        frames = find_frames(rising, threshold)
        bits_per_frame = [len(f) for f in frames]
        if bits_per_frame:
            unique_counts = sorted(set(bits_per_frame))
            print(f"\nGap threshold {threshold_mult}x ({threshold/4:.0f}us): "
                  f"{len(frames)} frames, "
                  f"bits/frame: {unique_counts}")

            # Show first few frames if they look like GS510SZ (39 or 42 bits)
            if any(28 <= c <= 50 for c in unique_counts):
                print("  ** Matches expected GS510SZ range (39-42 bits)! **")

                # Decode first few frames
                for fi, frame_edges in enumerate(frames[:5]):
                    bits = []
                    for edge_idx in frame_edges:
                        if edge_idx < len(data):
                            bits.append(data[edge_idx])
                    bit_str = "".join(str(b) for b in bits)
                    display = decode_display(bits)
                    print(f"  Frame {fi}: {len(bits)} bits = [{bit_str}]")
                    print(f"           display = '{display}'")

                    # Show status bits if we have enough
                    if len(bits) >= 35:
                        status = bits[28:]
                        print(f"           status bits = {status}")

    # Also try sampling on falling edges
    print(f"\n--- Sampling on falling edges ---")
    frames_fall = find_frames(falling, int(avg_gap * 10) if gaps else 1000)
    if frames_fall:
        bits_per_frame = [len(f) for f in frames_fall]
        unique_counts = sorted(set(bits_per_frame))
        print(f"Falling edge frames: {len(frames_fall)}, bits/frame: {unique_counts}")

        if any(28 <= c <= 50 for c in unique_counts):
            for fi, frame_edges in enumerate(frames_fall[:3]):
                bits = []
                for edge_idx in frame_edges:
                    if edge_idx < len(data):
                        bits.append(data[edge_idx])
                display = decode_display(bits)
                print(f"  Frame {fi}: {len(bits)} bits, display = '{display}'")


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else CSV_PATH
    print(f"Loading {path}...")
    ch4, ch5 = load_channels(path)
    print(f"Loaded {len(ch4)} samples ({len(ch4)/SAMPLE_RATE*1000:.1f}ms)")

    # Count transitions on each channel
    ch4_transitions = sum(1 for i in range(1, len(ch4)) if ch4[i] != ch4[i - 1])
    ch5_transitions = sum(1 for i in range(1, len(ch5)) if ch5[i] != ch5[i - 1])
    print(f"CH4 (Pin 5) transitions: {ch4_transitions}")
    print(f"CH5 (Pin 6) transitions: {ch5_transitions}")

    # Try both orderings
    analyze_clock_data(ch5, ch4, "CH5=Clock (Pin 6), CH4=Data (Pin 5)")
    analyze_clock_data(ch4, ch5, "CH4=Clock (Pin 5), CH5=Data (Pin 6)")


if __name__ == "__main__":
    main()
