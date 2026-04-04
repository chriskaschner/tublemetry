#!/usr/bin/env python3
"""Interactive ladder capture using sigrok-cli logic analyzer.

Prompts for temperature, captures until you press Enter, decodes, repeats.

Usage:
    uv run python 485/scripts/ladder_sigrok.py
"""

import json
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

SAMPLE_RATE = 1_000_000
CAPTURES_DIR = Path("485/captures")

SEG_TABLE = {
    0x7E: "0", 0x30: "1", 0x6D: "2", 0x79: "3", 0x33: "4",
    0x5B: "5", 0x5F: "6", 0x70: "7", 0x7F: "8", 0x73: "9",
    0x00: " ", 0x37: "H", 0x0E: "L", 0x4F: "E", 0x0D: "c", 0x0F: "t",
}


def decode_csv(csv_path: Path) -> list[str]:
    """Decode a 2-channel sigrok CSV into list of display strings per frame."""
    data_samples = []
    clk_samples = []
    for line in open(csv_path):
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        parts = line.split(",")
        try:
            d, c = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            continue
        data_samples.append(d)
        clk_samples.append(c)

    # Find clock rising edges
    rising = [i for i in range(1, len(clk_samples))
              if clk_samples[i - 1] == 0 and clk_samples[i] == 1]

    # Group into frames by gap
    if not rising:
        return []
    frames = []
    current = [rising[0]]
    for i in range(1, len(rising)):
        if rising[i] - rising[i - 1] > 2000:
            frames.append(current)
            current = [rising[i]]
        else:
            current.append(rising[i])
    if current:
        frames.append(current)

    # Decode each frame
    results = []
    for edges in frames:
        if len(edges) != 24:
            continue
        bits = [data_samples[e] if e < len(data_samples) else 0 for e in edges]
        display = ""
        for cs in range(0, 21, 7):
            val = 0
            for b in bits[cs:cs + 7]:
                val = (val << 1) | b
            display += SEG_TABLE.get(val, f"?0x{val:02X}")
        results.append(display)
    return results


def capture_and_decode(name: str) -> list[str]:
    """Run sigrok capture in continuous mode, export CSV, decode."""
    sr_path = CAPTURES_DIR / f"{name}.sr"
    csv_path = CAPTURES_DIR / f"{name}.csv"

    # Capture 10M samples (~10s at 1MHz)
    proc = subprocess.run(
        ["sigrok-cli", "-d", "fx2lafw", "-c", f"samplerate={SAMPLE_RATE}",
         "--samples", "10000000", "--channels", "D0,D1", "-o", str(sr_path)],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        print(f"  Capture error: {proc.stderr.strip()}")
        return []

    # Export to CSV
    proc = subprocess.run(
        ["sigrok-cli", "-i", str(sr_path), "-O", "csv"],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        print(f"  Export error: {proc.stderr.strip()}")
        return []
    csv_path.write_text(proc.stdout)

    return decode_csv(csv_path)


def main():
    CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")

    ladder = []

    print("Ladder Capture (sigrok)")
    print("=" * 40)
    print("1. Type the temperature showing on the display")
    print("2. Press Enter -- capture starts immediately (10s)")
    print("3. Press Temp Down DURING the capture to catch the flash")
    print("4. Type 'done' to finish and save results")
    print()

    while True:
        temp_str = input("Temperature showing (or 'done'): ").strip()
        if temp_str.lower() in ("done", "q", "quit"):
            break
        temp = temp_str  # accept any label (e.g. "Ec", "Sl", "104")

        print(f"  Capturing 10s... press Temp Down NOW if you want the flash")
        decoded = capture_and_decode(f"ladder_{date_str}_{temp}")

        if not decoded:
            print("  No frames decoded. Check connection.")
            continue

        counts = Counter(decoded)
        print(f"  {len(decoded)} frames decoded:")
        for display, count in counts.most_common():
            print(f"    \"{display}\" x{count}")
            if display not in [e["display"] for e in ladder]:
                ladder.append({
                    "temperature": temp,
                    "display": display,
                    "count": count,
                })

    if not ladder:
        print("\nNo data captured.")
        return

    # Save results
    json_path = CAPTURES_DIR / f"ladder_{date_str}.json"
    json.dump(ladder, open(json_path, "w"), indent=2)
    print(f"\nSaved: {json_path}")

    # Summary
    print(f"\n{'=' * 40}")
    print("LADDER SUMMARY")
    print(f"{'=' * 40}")
    confirmed = {}
    for entry in ladder:
        d = entry["display"]
        if len(d) == 3 and all(c in "0123456789 " for c in d):
            for i, ch in enumerate(d):
                # extract the 7-seg value would need raw bits, but we have the decoded char
                confirmed[f"pos{i}:{ch}"] = True
            print(f"  {entry['temperature']}F -> \"{d}\" (x{entry['count']})")
        else:
            print(f"  {entry['temperature']}F -> \"{d}\" (x{entry['count']}) [non-numeric]")

    unique_digits = set()
    for entry in ladder:
        for ch in entry["display"]:
            if ch in "0123456789":
                unique_digits.add(ch)
    print(f"\nDigits confirmed: {sorted(unique_digits)}")
    missing = set("0123456789") - unique_digits
    if missing:
        print(f"Still need: {sorted(missing)}")
    else:
        print("All digits 0-9 confirmed!")


if __name__ == "__main__":
    main()
