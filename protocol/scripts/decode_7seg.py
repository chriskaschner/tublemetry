"""
Decode 7-segment display data from Balboa VS300FL4 hot tub controller.
Logic analyzer capture: 1MHz, 10s, 8 channels. OH.csv file.
CH4 = display content RS-485 stream, CH5 = display refresh RS-485 stream.
"""

import numpy as np
import sys
from collections import Counter

CSV_PATH = r"C:\Users\ckaschner\OneDrive - Electronic Theatre Controls, Inc\Desktop\485\OH.csv"

# --- Load data efficiently ---
print("Loading CSV (10M rows)... ", end="", flush=True)
# Skip header row; columns are CH0-CH7 (indices 0-7)
data = np.loadtxt(CSV_PATH, delimiter=",", skiprows=1, dtype=np.uint8)
print(f"done. Shape: {data.shape}")

ch4 = data[:, 4]  # CH4 - display content
ch5 = data[:, 5]  # CH5 - display refresh

SAMPLE_RATE = 1_000_000  # 1 MHz
BAUD = 115200
SAMPLES_PER_BIT = SAMPLE_RATE / BAUD  # ~8.68

# --- Find bursts (clusters of transitions) ---
def find_bursts(signal, min_gap_us=500, min_transitions=5):
    """Find bursts of activity in a signal.
    A burst is a region with transitions, separated by gaps of at least min_gap_us microseconds.
    Returns list of (start_idx, end_idx) tuples.
    """
    # Find all transition points
    transitions = np.where(np.diff(signal) != 0)[0]
    if len(transitions) == 0:
        return []

    min_gap = int(min_gap_us)  # at 1MHz, 1 sample = 1 us
    # Split into bursts by gaps
    gaps = np.diff(transitions)
    split_points = np.where(gaps > min_gap)[0]

    bursts = []
    start = 0
    for sp in split_points:
        end = sp + 1
        if end - start >= min_transitions:
            bursts.append((transitions[start], transitions[end - 1]))
        start = end
    # Last burst
    if len(transitions) - start >= min_transitions:
        bursts.append((transitions[start], transitions[-1]))

    return bursts


def uart_decode_region(signal, start, end, polarity="idle_high"):
    """
    Attempt UART decode of a signal region at 115200 baud.
    polarity: 'idle_high' means idle=1, start bit=0->1 transition not needed, start bit is 0.
              'idle_low' means idle=0, start bit=1 (inverted).
    Returns list of decoded bytes.
    """
    spb = SAMPLES_PER_BIT
    region = signal[start:end + 1].copy()

    if polarity == "idle_low":
        region = 1 - region  # invert

    # Now we work in idle_high convention: idle=1, start=0
    decoded = []
    i = 0
    while i < len(region) - int(spb * 10):
        # Look for falling edge (1 -> 0) = start bit
        if region[i] == 1 and region[i + 1] == 0:
            # Potential start bit at i+1
            start_bit_pos = i + 1
            # Verify start bit at center
            center = start_bit_pos + spb / 2
            if int(center) < len(region) and region[int(center)] == 0:
                # Sample 8 data bits (LSB first)
                byte_val = 0
                valid = True
                for bit_idx in range(8):
                    sample_pos = int(start_bit_pos + spb * (1 + bit_idx) + spb / 2)
                    if sample_pos >= len(region):
                        valid = False
                        break
                    if region[sample_pos] == 1:
                        byte_val |= (1 << bit_idx)

                if valid:
                    # Check stop bit
                    stop_pos = int(start_bit_pos + spb * 9 + spb / 2)
                    if stop_pos < len(region) and region[stop_pos] == 1:
                        decoded.append(byte_val)
                        # Advance past this byte
                        i = int(start_bit_pos + spb * 10)
                        continue
                    else:
                        # Stop bit wrong, but still record (framing error)
                        decoded.append(byte_val)
                        i = int(start_bit_pos + spb * 10)
                        continue
            # Not a valid start, advance
            i += 1
        else:
            i += 1

    return decoded


def analyze_channel(name, signal):
    print(f"\n{'='*70}")
    print(f"Analyzing {name}")
    print(f"{'='*70}")

    # Basic stats
    ones = np.sum(signal)
    zeros = len(signal) - ones
    print(f"Total samples: {len(signal):,}  |  1s: {ones:,}  |  0s: {zeros:,}")

    # Determine idle state
    idle_val = 1 if ones > zeros else 0
    print(f"Idle state appears to be: {idle_val}")

    # Find transitions
    transitions = np.where(np.diff(signal) != 0)[0]
    print(f"Total transitions: {len(transitions):,}")

    if len(transitions) == 0:
        print("No transitions found - channel is static.")
        return

    # Find bursts with a moderate gap threshold
    # For RS-485 UART at 115200, one byte = ~87us. Gap between bytes in a frame: maybe 10-100us.
    # Gap between frames: maybe 1-10ms. Gap between on/off phases: ~500ms.
    # Use 1000us (1ms) to separate individual frames/bursts
    bursts_fine = find_bursts(signal, min_gap_us=200, min_transitions=3)
    print(f"Bursts (>200us gap): {len(bursts_fine)}")

    if len(bursts_fine) == 0:
        print("No bursts found.")
        return

    # Print burst timing overview
    burst_starts_s = [b[0] / SAMPLE_RATE for b in bursts_fine]
    burst_durations_us = [(b[1] - b[0]) for b in bursts_fine]

    print(f"\nFirst 20 burst times (seconds) and durations (us):")
    for i, (bs, bd) in enumerate(zip(burst_starts_s[:20], burst_durations_us[:20])):
        trans_count = np.sum(np.diff(signal[bursts_fine[i][0]:bursts_fine[i][1]+1]) != 0)
        print(f"  Burst {i:3d}: t={bs:8.4f}s  dur={bd:7d}us  transitions={trans_count}")

    # Group bursts into "on" and "off" phases
    # The display flashes ~500ms on, ~500ms off -> ~1Hz
    # Find large gaps between burst clusters
    if len(bursts_fine) > 1:
        burst_gaps = [bursts_fine[i+1][0] - bursts_fine[i][1] for i in range(len(bursts_fine)-1)]
        large_gap_threshold = 100_000  # 100ms - between on/off phases
        phase_boundaries = [i for i, g in enumerate(burst_gaps) if g > large_gap_threshold]

        print(f"\nLarge gaps (>100ms): {len(phase_boundaries)}")
        for i, pb in enumerate(phase_boundaries[:20]):
            gap_ms = burst_gaps[pb] / 1000
            print(f"  After burst {pb}: gap = {gap_ms:.1f}ms")

    # --- UART Decoding ---
    print(f"\n--- UART Decode Attempts ---")

    # Try both polarities on a sample of bursts
    for polarity in ["idle_high", "idle_low"]:
        all_bytes = []
        bytes_per_burst = []
        for b_start, b_end in bursts_fine[:50]:  # First 50 bursts
            decoded = uart_decode_region(signal, b_start, b_end, polarity)
            all_bytes.extend(decoded)
            bytes_per_burst.append(decoded)

        if all_bytes:
            byte_counts = Counter(all_bytes)
            unique_bytes = len(byte_counts)
            print(f"\n  Polarity: {polarity}")
            print(f"  Decoded {len(all_bytes)} bytes from first 50 bursts, {unique_bytes} unique values")
            print(f"  Most common bytes: {byte_counts.most_common(15)}")

            # Show first few frames
            print(f"  First 15 burst decodes:")
            for i, fb in enumerate(bytes_per_burst[:15]):
                hex_str = " ".join(f"{b:02X}" for b in fb)
                t_s = bursts_fine[i][0] / SAMPLE_RATE
                print(f"    Burst {i} (t={t_s:.4f}s): [{hex_str}]")
        else:
            print(f"\n  Polarity: {polarity} -> No bytes decoded")

    # --- Raw pattern analysis (fallback) ---
    print(f"\n--- Raw Burst Pattern Analysis ---")

    # For each burst, extract a compact representation
    patterns = []
    for idx, (b_start, b_end) in enumerate(bursts_fine[:100]):
        seg = signal[b_start:b_end+1]
        # Run-length encode
        changes = np.where(np.diff(seg) != 0)[0]
        runs = []
        prev = 0
        for c in changes:
            runs.append((int(seg[prev]), c - prev + 1))
            prev = c + 1
        runs.append((int(seg[prev]), len(seg) - prev))
        patterns.append((idx, b_start, runs))

    # Show first 15 patterns with run lengths
    print(f"First 15 burst run-length patterns (value, length_in_samples):")
    for idx, b_start, runs in patterns[:15]:
        t_s = b_start / SAMPLE_RATE
        # Compact display: show runs as bit_value:length
        compact = " ".join(f"{v}:{l}" for v, l in runs[:40])
        if len(runs) > 40:
            compact += f" ... ({len(runs)} runs total)"
        print(f"  Burst {idx} (t={t_s:.4f}s, {len(runs)} runs): {compact}")

    # --- Attempt to decode run-length patterns as UART ---
    print(f"\n--- Run-Length UART Interpretation ---")
    print("Attempting to interpret run lengths as multiples of bit period (~8.68 samples)...")

    for idx, b_start, runs in patterns[:15]:
        t_s = b_start / SAMPLE_RATE
        # Convert run lengths to approximate bit counts
        bit_runs = [(v, round(l / SAMPLES_PER_BIT, 1)) for v, l in runs]
        compact = " ".join(f"{v}:{b:.1f}b" for v, b in bit_runs[:40])
        if len(bit_runs) > 40:
            compact += " ..."
        print(f"  Burst {idx} (t={t_s:.4f}s): {compact}")

    # --- Phase-separated analysis ---
    if len(bursts_fine) > 1 and phase_boundaries:
        print(f"\n--- Phase Analysis (On vs Off) ---")
        # Group bursts into phases
        phases = []
        prev_idx = 0
        for pb in phase_boundaries:
            phases.append(bursts_fine[prev_idx:pb+1])
            prev_idx = pb + 1
        phases.append(bursts_fine[prev_idx:])

        print(f"Found {len(phases)} phases")
        for pi, phase in enumerate(phases[:10]):
            if not phase:
                continue
            phase_start = phase[0][0] / SAMPLE_RATE
            phase_end = phase[-1][1] / SAMPLE_RATE
            dur = phase_end - phase_start
            print(f"\n  Phase {pi}: t={phase_start:.3f}-{phase_end:.3f}s ({dur*1000:.0f}ms), {len(phase)} bursts")

            # UART decode all bursts in this phase (try both polarities)
            for polarity in ["idle_high", "idle_low"]:
                phase_bytes = []
                per_burst = []
                for b_start, b_end in phase[:20]:
                    decoded = uart_decode_region(signal, b_start, b_end, polarity)
                    phase_bytes.extend(decoded)
                    per_burst.append(decoded)

                if phase_bytes:
                    unique = len(set(phase_bytes))
                    # Only show if there's some variety
                    if unique > 1 or (unique == 1 and phase_bytes[0] != 0 and phase_bytes[0] != 0xFF):
                        print(f"    {polarity}: {len(phase_bytes)} bytes, {unique} unique")
                        # Show first few
                        for bi, fb in enumerate(per_burst[:5]):
                            if fb:
                                hex_str = " ".join(f"{b:02X}" for b in fb)
                                print(f"      Burst {bi}: [{hex_str}]")

    # --- Transition density analysis ---
    print(f"\n--- Transition Density Over Time ---")
    # Bin transitions into 10ms windows
    window_us = 10_000
    max_sample = len(signal)
    n_windows = max_sample // window_us
    trans_density = np.zeros(n_windows, dtype=np.int32)
    for t in transitions:
        win = t // window_us
        if win < n_windows:
            trans_density[win] += 1

    # Find windows with activity
    active_windows = np.where(trans_density > 0)[0]
    if len(active_windows) > 0:
        print(f"Active windows (10ms bins): {len(active_windows)} of {n_windows}")
        # Show transition density pattern at 100ms resolution
        window_100ms = 100_000
        n_w100 = max_sample // window_100ms
        td100 = np.zeros(n_w100, dtype=np.int32)
        for t in transitions:
            w = t // window_100ms
            if w < n_w100:
                td100[w] += 1

        print("Transition density per 100ms window:")
        for i in range(min(n_w100, 100)):
            if td100[i] > 0:
                bar = "#" * min(td100[i] // 10, 60)
                print(f"  {i*0.1:5.1f}s: {td100[i]:5d} {bar}")


# Analyze both channels
analyze_channel("CH4 (Pin 5 - Display Content)", ch4)
analyze_channel("CH5 (Pin 6 - Display Refresh)", ch5)

print("\n\nDone.")
