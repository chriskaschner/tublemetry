"""Scan hex.txt for any bytes deviating from the known repeating pattern."""

import re

HEX_FILE = r"C:\Users\ckaschner\OneDrive - Electronic Theatre Controls, Inc\Desktop\485\hex.txt"
KNOWN_PATTERN = [0xFE, 0x06, 0x70, 0x30, 0x00, 0x06, 0x70, 0x00]
KNOWN_SET = set(KNOWN_PATTERN)

all_bytes = []

with open(HEX_FILE, "r") as f:
    for line in f:
        line = line.rstrip("\n\r")
        if not line.strip():
            continue
        # TeraTerm format: "OFFSET\thex hex hex ...  hex hex hex ...   ASCII"
        # Split on tab to get offset and the rest
        parts = line.split("\t", 1)
        if len(parts) < 2:
            continue
        rest = parts[1]
        # The ASCII display starts after 3 spaces following the hex block
        # Find the ASCII portion (after "   " triple-space separator)
        ascii_idx = rest.rfind("   ")
        if ascii_idx >= 0:
            hex_part = rest[:ascii_idx]
        else:
            hex_part = rest
        # Parse hex bytes (skip extra whitespace between the two 8-byte groups)
        tokens = hex_part.split()
        for tok in tokens:
            tok = tok.strip()
            if re.fullmatch(r"[0-9a-fA-F]{2}", tok):
                all_bytes.append(int(tok, 16))

total = len(all_bytes)
print(f"Total bytes parsed: {total}")
print(f"Total 8-byte frames: {total // 8} (remainder: {total % 8})")
print()

# Check 1: Any byte not in the known set?
anomalous_bytes = []
for i, b in enumerate(all_bytes):
    if b not in KNOWN_SET:
        anomalous_bytes.append((i, b))

if anomalous_bytes:
    print(f"ANOMALOUS BYTES FOUND: {len(anomalous_bytes)}")
    for offset, val in anomalous_bytes[:50]:  # cap output at 50
        print(f"  Offset 0x{offset:04X} ({offset:>6d}): 0x{val:02X}")
    if len(anomalous_bytes) > 50:
        print(f"  ... and {len(anomalous_bytes) - 50} more")
else:
    print("No anomalous bytes — every byte is in {fe, 06, 70, 30, 00}.")

print()

# Check 2: Does the 8-byte pattern ever deviate?
pattern_deviations = []
for frame_idx in range(total // 8):
    start = frame_idx * 8
    frame = all_bytes[start:start + 8]
    if frame != KNOWN_PATTERN:
        pattern_deviations.append((frame_idx, start, frame))

if pattern_deviations:
    print(f"PATTERN DEVIATIONS FOUND: {len(pattern_deviations)}")
    for frame_idx, offset, frame in pattern_deviations[:50]:
        hex_str = " ".join(f"{b:02x}" for b in frame)
        print(f"  Frame {frame_idx:>5d} (offset 0x{offset:04X}): {hex_str}")
    if len(pattern_deviations) > 50:
        print(f"  ... and {len(pattern_deviations) - 50} more")
else:
    print("No pattern deviations — every 8-byte frame matches fe 06 70 30 00 06 70 00.")

# Remainder bytes (if total not multiple of 8)
rem = total % 8
if rem:
    tail = all_bytes[-(rem):]
    hex_str = " ".join(f"{b:02x}" for b in tail)
    print(f"\nTrailing {rem} bytes (incomplete frame): {hex_str}")
