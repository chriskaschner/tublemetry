"""
Scan teraterm.txt for non-idle patterns.

TeraTerm mangled the RS-485 data via UTF-8 encoding:
- 0xFE -> EF BF BD (replacement char)
- 0x06, 0x00 -> stripped (control chars)
- 0x70 -> 'p' (0x70), 0x30 -> '0' (0x30) preserved as ASCII

Idle pattern in the hex dump: "ef bf bd 70 30 70" repeating
We want to find lines that deviate from this pattern.
"""
import re

filepath = r"C:\Users\ckaschner\OneDrive - Electronic Theatre Controls, Inc\Desktop\485\teraterm.txt"

with open(filepath, 'r') as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")
print()

# The hex portion is the first ~48 chars of each line (after the offset)
# Format: "0000\tXX XX XX XX XX XX XX XX  XX XX XX XX XX XX XX XX   ASCII"

idle_hex_bytes = {'ef', 'bf', 'bd', '70', '30'}  # bytes in the idle pattern
non_idle_lines = []

for i, line in enumerate(lines):
    line = line.strip()
    if not line:
        continue

    # Extract hex bytes from the line
    # Format: offset\thex_bytes   ascii
    parts = line.split('\t')
    if len(parts) < 2:
        continue

    hex_part = parts[1].split('   ')[0] if '   ' in parts[1] else parts[1]
    hex_bytes = hex_part.replace('  ', ' ').split()

    # Check for any non-idle bytes
    non_idle = [b for b in hex_bytes if b.lower() not in idle_hex_bytes]

    if non_idle:
        non_idle_lines.append((i + 1, line, non_idle))

print(f"Lines with non-idle bytes: {len(non_idle_lines)}")
print()

# Show all non-idle lines with context
prev_printed = -10
for line_num, line, non_idle_bytes in non_idle_lines:
    if line_num - prev_printed > 2:
        print()  # visual separator
    print(f"  L{line_num:4d}: {line[:80]}")
    print(f"         Non-idle bytes: {' '.join(non_idle_bytes)}")
    prev_printed = line_num

# Also collect all unique byte values found
all_bytes = set()
for i, line in enumerate(lines):
    line = line.strip()
    if not line:
        continue
    parts = line.split('\t')
    if len(parts) < 2:
        continue
    hex_part = parts[1].split('   ')[0] if '   ' in parts[1] else parts[1]
    hex_bytes = hex_part.replace('  ', ' ').split()
    for b in hex_bytes:
        try:
            all_bytes.add(int(b, 16))
        except ValueError:
            pass

print(f"\n\nAll unique byte values in teraterm.txt:")
print("  " + " ".join(f"0x{b:02X}" for b in sorted(all_bytes)))
print(f"  ({len(all_bytes)} unique values)")

# Show which are idle vs non-idle
idle_set = {0xEF, 0xBF, 0xBD, 0x70, 0x30}
non_idle_set = all_bytes - idle_set
print(f"\nNon-idle bytes: {' '.join(f'0x{b:02X}' for b in sorted(non_idle_set))}")
