#!/usr/bin/env python3
"""Temperature ladder capture script for VS300FL4 hot tub.

Guides the user through a structured temperature sweep (104 -> 80F),
capturing RS-485 frames at each step to build a verified 7-segment
byte-to-digit lookup table.

This module is structured for testability:
  - All logic is in pure functions (parse, validate, output)
  - Serial I/O is isolated in main() -- only used when run as CLI
  - Tests import the pure functions directly

Usage:
    uv run python 485/scripts/ladder_capture.py --help
    uv run python 485/scripts/ladder_capture.py --port /dev/ttyUSB0
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import IO, Any

# Reference table for cross-checking results
# Imported lazily to avoid import errors when tubtron package isn't installed
_SEVEN_SEG_TABLE: dict[int, str] | None = None


def _get_seven_seg_table() -> dict[int, str]:
    """Lazy-load the SEVEN_SEG_TABLE from tubtron.decode."""
    global _SEVEN_SEG_TABLE
    if _SEVEN_SEG_TABLE is None:
        try:
            from tubtron.decode import SEVEN_SEG_TABLE

            _SEVEN_SEG_TABLE = SEVEN_SEG_TABLE
        except ImportError:
            # Fallback: inline the reference table for standalone use
            _SEVEN_SEG_TABLE = {
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
                0x00: " ",
            }
    return _SEVEN_SEG_TABLE


# ---------------------------------------------------------------------------
# Capture line regex: matches "[   1.234] (  8 bytes) FE 06 70 E6 00 06 70 00"
# ---------------------------------------------------------------------------
_CAPTURE_LINE_RE = re.compile(
    r"^\[\s*(\d+\.\d+)\]\s*\(\s*(\d+)\s*bytes?\)\s+([0-9A-Fa-f ]+)$"
)


def parse_capture_line(line: str) -> dict[str, Any] | None:
    """Parse a formatted capture line into structured data.

    Args:
        line: A capture line like "[   1.234] (  8 bytes) FE 06 70 E6 00 06 70 00"

    Returns:
        Dict with keys: timestamp (float), byte_count (int), raw_bytes (bytes).
        None if the line does not match the expected format.
    """
    if not line or not line.strip():
        return None

    match = _CAPTURE_LINE_RE.match(line.strip())
    if not match:
        return None

    timestamp = float(match.group(1))
    byte_count = int(match.group(2))
    hex_str = match.group(3).strip()
    raw_bytes = bytes(int(b, 16) for b in hex_str.split())

    return {
        "timestamp": timestamp,
        "byte_count": byte_count,
        "raw_bytes": raw_bytes,
    }


def extract_stable_frames(
    parsed_frames: list[dict[str, Any]], min_consecutive: int = 3
) -> list[dict[str, Any]]:
    """Find groups of consecutive identical frames (stability detection).

    A "stable" reading is one where the same 8-byte frame appears
    min_consecutive or more times in a row. This filters out transition
    frames captured while the display is updating.

    Args:
        parsed_frames: List of dicts from parse_capture_line().
        min_consecutive: Minimum consecutive identical frames for stability.

    Returns:
        List of dicts with keys: frame (bytes), count (int), first_timestamp (float).
    """
    if not parsed_frames:
        return []

    stable_groups: list[dict[str, Any]] = []
    current_frame = parsed_frames[0]["raw_bytes"]
    current_count = 1
    first_timestamp = parsed_frames[0]["timestamp"]

    for i in range(1, len(parsed_frames)):
        frame = parsed_frames[i]["raw_bytes"]
        if frame == current_frame:
            current_count += 1
        else:
            if current_count >= min_consecutive:
                stable_groups.append(
                    {
                        "frame": current_frame,
                        "count": current_count,
                        "first_timestamp": first_timestamp,
                    }
                )
            current_frame = frame
            current_count = 1
            first_timestamp = parsed_frames[i]["timestamp"]

    # Check the last group
    if current_count >= min_consecutive:
        stable_groups.append(
            {
                "frame": current_frame,
                "count": current_count,
                "first_timestamp": first_timestamp,
            }
        )

    return stable_groups


def build_ladder_entry(
    temperature: int,
    stable_frames: list[bytes],
    timestamp: float,
) -> dict[str, Any]:
    """Create a structured ladder entry from a stable capture at a known temperature.

    Args:
        temperature: The known temperature displayed on the panel (e.g., 104).
        stable_frames: List of identical 8-byte frames captured at this temperature.
        timestamp: Timestamp of the first stable frame.

    Returns:
        Dict with keys: temperature, stable_frames, raw_hex, byte_3_value, timestamp.
    """
    representative = stable_frames[0]
    raw_hex = " ".join(f"{b:02X}" for b in representative)

    return {
        "temperature": temperature,
        "stable_frames": stable_frames,
        "raw_hex": raw_hex,
        "byte_3_value": representative[3] if len(representative) > 3 else 0,
        "timestamp": timestamp,
        "stable_frame_count": len(stable_frames),
    }


def validate_ladder(
    ladder: list[dict[str, Any]], min_temperatures: int = 5
) -> tuple[bool, list[str]]:
    """Validate that a completed ladder has sufficient coverage.

    Args:
        ladder: List of ladder entries from build_ladder_entry().
        min_temperatures: Minimum distinct temperatures required.

    Returns:
        Tuple of (is_valid, error_messages).
    """
    errors: list[str] = []

    if not ladder:
        errors.append("Ladder is empty -- no temperature entries captured")
        return False, errors

    temperatures = {entry["temperature"] for entry in ladder}
    if len(temperatures) < min_temperatures:
        errors.append(
            f"Only {len(temperatures)} distinct temperatures captured; "
            f"need at least {min_temperatures}"
        )

    byte3_values = {entry["byte_3_value"] for entry in ladder}
    if len(byte3_values) < min_temperatures:
        errors.append(
            f"Only {len(byte3_values)} unique byte_3 values seen; "
            f"need at least {min_temperatures} for meaningful coverage"
        )

    is_valid = len(errors) == 0
    return is_valid, errors


def generate_lookup_update(
    ladder: list[dict[str, Any]],
) -> dict[int, str]:
    """Generate a byte-to-digit mapping from a validated ladder.

    For each temperature in the ladder, extracts the ones digit and maps
    the byte_3 value to that digit character. This builds the confirmed
    lookup table entries.

    Args:
        ladder: List of ladder entries from build_ladder_entry().

    Returns:
        Dict mapping byte values (int) to digit characters (str).
    """
    lookup: dict[int, str] = {}
    reference = _get_seven_seg_table()

    for entry in ladder:
        temp = entry["temperature"]
        byte_3 = entry["byte_3_value"]
        ones_digit = str(temp % 10)

        lookup[byte_3] = ones_digit

    return lookup


def write_ladder_csv(
    ladder: list[dict[str, Any]],
    output: IO[str],
) -> None:
    """Write ladder entries to CSV format.

    Args:
        ladder: List of ladder entries from build_ladder_entry().
        output: File-like object to write CSV data to.
    """
    fieldnames = [
        "temperature",
        "byte_0",
        "byte_1",
        "byte_2",
        "byte_3",
        "byte_4",
        "byte_5",
        "byte_6",
        "byte_7",
        "stable_frame_count",
        "timestamp",
    ]

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for entry in ladder:
        frame = entry["stable_frames"][0]
        row = {
            "temperature": entry["temperature"],
            "stable_frame_count": entry.get("stable_frame_count", len(entry["stable_frames"])),
            "timestamp": entry.get("timestamp", 0.0),
        }
        for i in range(8):
            row[f"byte_{i}"] = f"0x{frame[i]:02X}" if i < len(frame) else ""
        writer.writerow(row)


def _print_summary(
    lookup: dict[int, str],
) -> None:
    """Print a summary of confirmed vs unverified SEVEN_SEG_TABLE entries."""
    reference = _get_seven_seg_table()
    print("\n" + "=" * 60)
    print("LADDER CAPTURE SUMMARY")
    print("=" * 60)

    confirmed = []
    unverified = []
    mismatches = []

    for byte_val, ref_char in sorted(reference.items()):
        if byte_val in lookup:
            if lookup[byte_val] == ref_char:
                confirmed.append((byte_val, ref_char))
            else:
                mismatches.append((byte_val, ref_char, lookup[byte_val]))
        else:
            unverified.append((byte_val, ref_char))

    print(f"\nConfirmed ({len(confirmed)}):")
    for bv, char in confirmed:
        print(f"  0x{bv:02X} = '{char}'")

    if mismatches:
        print(f"\nMISMATCHES ({len(mismatches)}) -- GS510SZ reference does NOT match:")
        for bv, ref_char, actual_char in mismatches:
            print(f"  0x{bv:02X}: reference='{ref_char}', captured='{actual_char}'")

    print(f"\nStill unverified ({len(unverified)}):")
    for bv, char in unverified:
        print(f"  0x{bv:02X} = '{char}' (GS510SZ reference)")

    print()


def main() -> None:
    """CLI entry point: guided temperature ladder capture."""
    parser = argparse.ArgumentParser(
        description="Temperature ladder capture for VS300FL4 hot tub. "
        "Guides you through a structured temperature sweep to build "
        "a verified 7-segment byte-to-digit lookup table.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Example:
  uv run python 485/scripts/ladder_capture.py --port /dev/ttyUSB0
  uv run python 485/scripts/ladder_capture.py --port /dev/cu.usbserial-1420 --start 104 --end 95

The script will:
  1. Prompt you to confirm the displayed temperature at each step
  2. Capture RS-485 frames for 3 seconds at each temperature
  3. Detect stable frames (3+ consecutive identical 8-byte frames)
  4. Build a verified byte-to-digit mapping
  5. Output CSV + JSON results
""",
    )
    parser.add_argument(
        "--port",
        default="/dev/ttyUSB0",
        help="Serial port for RS-485 adapter (default: /dev/ttyUSB0)",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="Baud rate (default: 115200)",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=104,
        help="Starting temperature in F (default: 104)",
    )
    parser.add_argument(
        "--end",
        type=int,
        default=80,
        help="Ending temperature in F (default: 80)",
    )
    parser.add_argument(
        "--capture-seconds",
        type=float,
        default=3.0,
        help="Seconds to capture at each temperature (default: 3.0)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("485/captures"),
        help="Output directory for CSV and JSON (default: 485/captures)",
    )

    args = parser.parse_args()

    # If --help was shown, we exit before needing serial
    # Import serial only when actually running the capture
    try:
        import serial
    except ImportError:
        print("ERROR: pyserial is required for capture mode.")
        print("Install with: uv add pyserial")
        sys.exit(1)

    print("VS300FL4 Temperature Ladder Capture")
    print("=" * 50)
    print(f"Port: {args.port}")
    print(f"Baud: {args.baud}")
    print(f"Range: {args.start}F -> {args.end}F")
    print(f"Capture duration: {args.capture_seconds}s per step")
    print()

    try:
        ser = serial.Serial(
            port=args.port,
            baudrate=args.baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.1,
        )
    except serial.SerialException as e:
        print(f"ERROR: Could not open serial port {args.port}: {e}")
        sys.exit(1)

    ser.reset_input_buffer()
    ladder: list[dict] = []
    import time

    step = -1 if args.start > args.end else 1
    temps = list(range(args.start, args.end + step, step))

    for temp in temps:
        print(f"\n--- Temperature: {temp}F ---")
        input(f"Confirm the panel shows {temp}F, then press Enter to capture...")

        # Capture frames for the specified duration
        frames: list[dict] = []
        start_time = time.time()
        while time.time() - start_time < args.capture_seconds:
            data = ser.read(256)
            if data and len(data) >= 8:
                elapsed = time.time() - start_time
                # Parse 8-byte frames from the data
                for offset in range(0, len(data) - 7, 8):
                    chunk = data[offset : offset + 8]
                    if len(chunk) == 8:
                        frames.append(
                            {
                                "timestamp": elapsed,
                                "byte_count": 8,
                                "raw_bytes": bytes(chunk),
                            }
                        )

        stable = extract_stable_frames(frames)
        if stable:
            best = max(stable, key=lambda s: s["count"])
            entry = build_ladder_entry(
                temperature=temp,
                stable_frames=[best["frame"]] * best["count"],
                timestamp=best["first_timestamp"],
            )
            ladder.append(entry)
            print(
                f"  Captured: {entry['raw_hex']} "
                f"({best['count']} stable frames)"
            )
        else:
            print(f"  WARNING: No stable frames detected at {temp}F")
            print("  Try waiting longer or checking connection.")

        if temp != temps[-1]:
            input("Press Temp Down, wait for display to settle, then press Enter...")

    ser.close()

    # Validate and generate results
    is_valid, errors = validate_ladder(ladder)
    if not is_valid:
        print("\nLadder validation FAILED:")
        for err in errors:
            print(f"  - {err}")
    else:
        print("\nLadder validation PASSED")

    lookup = generate_lookup_update(ladder)

    # Output files
    args.output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")

    csv_path = args.output_dir / f"ladder_{date_str}.csv"
    with open(csv_path, "w", newline="") as f:
        write_ladder_csv(ladder, f)
    print(f"\nCSV saved: {csv_path}")

    json_path = args.output_dir / f"ladder_{date_str}.json"
    json_data = {
        "capture_date": date_str,
        "port": args.port,
        "temperature_range": f"{args.start}-{args.end}F",
        "entries": len(ladder),
        "lookup": {f"0x{k:02X}": v for k, v in lookup.items()},
        "valid": is_valid,
        "errors": errors,
    }
    with open(json_path, "w") as f:
        json.dump(json_data, f, indent=2)
    print(f"JSON saved: {json_path}")

    _print_summary(lookup)


if __name__ == "__main__":
    main()
