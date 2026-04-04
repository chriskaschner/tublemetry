"""
Brute-force 7-segment decoder for Balboa VS300FL4.

We have two reliable RS-485 adapter captures (idle frames):
  Frame A (hex.txt):          FE 06 70 30 00 06 70 00
  Frame B (rs485_capture.txt): FE 06 70 E6 00 06 70 00

Only byte index 3 differs: 0x30 vs 0xE6. This must be a digit that
changed when the temperature changed. The other bytes are constant.

We also know:
  - Lights toggle causes FE to disappear (status/indicator byte)
  - Temp range: 80-106°F (3-digit display)
  - The display shows "OH" during overheat (2 characters)

Approach: try all 7! = 5040 permutations of segment-to-bit mapping,
combined with all possible choices of which byte positions are digits.
Find mappings that produce valid temperature readings for both frames.
"""
from itertools import permutations

# Standard 7-segment digit definitions
# Each digit is a frozenset of segment names
DIGIT_SEGMENTS = {
    '0': frozenset('abcdef'),
    '1': frozenset('bc'),
    '2': frozenset('abdeg'),
    '3': frozenset('abcdg'),
    '4': frozenset('bcfg'),
    '5': frozenset('acdfg'),
    '6': frozenset('acdefg'),
    '7': frozenset('abc'),
    '8': frozenset('abcdefg'),
    '9': frozenset('abcdfg'),
}

# Letters for error codes
LETTER_SEGMENTS = {
    'O': frozenset('abcdef'),   # same as 0
    'H': frozenset('bcefg'),
    'P': frozenset('abefg'),
    'r': frozenset('eg'),
    'E': frozenset('adefg'),
    'F': frozenset('aefg'),
    'C': frozenset('adef'),
    'A': frozenset('abcefg'),
    'L': frozenset('def'),
    'n': frozenset('ceg'),
    'o': frozenset('cdeg'),     # lowercase o
    'b': frozenset('cdefg'),
    'd': frozenset('bcdeg'),
    '-': frozenset('g'),        # dash/minus
    ' ': frozenset(),           # blank
}

ALL_CHARS = {}
ALL_CHARS.update(DIGIT_SEGMENTS)
ALL_CHARS.update(LETTER_SEGMENTS)

SEGMENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g']

# Our two known idle frames (from RS-485 adapter, reliable)
FRAME_A = [0xFE, 0x06, 0x70, 0x30, 0x00, 0x06, 0x70, 0x00]  # hex.txt
FRAME_B = [0xFE, 0x06, 0x70, 0xE6, 0x00, 0x06, 0x70, 0x00]  # rs485_capture.txt

# Temp-change frames (from rs485_capture.txt)
FRAME_TEMP_DOWN = [0x06, 0x70, 0xE6, 0x00, 0x00, 0x06, 0x00, 0xF3]
FRAME_TEMP_UP   = [0x06, 0x70, 0xE6, 0x00, 0x00, 0x03, 0x18, 0x00]


def byte_to_segments(byte_val, mapping):
    """Given a byte and a mapping (segment->bit), return set of active segments.
    Bit 7 is assumed to be dp/indicator, not a segment."""
    segs = set()
    for seg, bit in mapping.items():
        if byte_val & (1 << bit):
            segs.add(seg)
    return frozenset(segs)


def segments_to_char(seg_set):
    """Look up what character a segment set represents. Returns None if no match."""
    for ch, segs in ALL_CHARS.items():
        if segs == seg_set:
            return ch
    return None


def try_mapping(mapping):
    """Try a specific segment-to-bit mapping against all our data.
    Returns results if it produces valid temperatures."""

    # For each byte value in our frames, decode to character
    unique_bytes = set()
    for frame in [FRAME_A, FRAME_B]:
        for b in frame:
            unique_bytes.add(b)

    # Decode each unique byte (strip bit 7 for segment matching)
    byte_chars = {}
    for bv in unique_bytes:
        lower7 = bv & 0x7F
        segs = byte_to_segments(lower7, mapping)
        ch = segments_to_char(segs)
        has_dp = bool(bv & 0x80)
        byte_chars[bv] = (ch, has_dp, segs)

    # Now try all combinations of 3 digit positions out of 8
    # But we know byte 3 changes between frames, so it MUST be a digit position
    # Also bytes 4,7 are 0x00 in both frames (blank) - could be digit or not

    results = []

    # Digit position 3 is forced (it's the byte that changes)
    # Need 2 more positions from {0, 1, 2, 5, 6} (skip 4,7 as they're always 0x00)
    from itertools import combinations
    for other_positions in combinations([0, 1, 2, 5, 6], 2):
        digit_positions = sorted(list(other_positions) + [3])

        # Decode frame A
        digits_a = []
        valid_a = True
        for pos in digit_positions:
            ch, dp, segs = byte_chars[FRAME_A[pos]]
            if ch is None or ch not in DIGIT_SEGMENTS:
                valid_a = False
                break
            digits_a.append(ch)
        if not valid_a:
            continue

        # Decode frame B
        digits_b = []
        valid_b = True
        for pos in digit_positions:
            ch, dp, segs = byte_chars[FRAME_B[pos]]
            if ch is None or ch not in DIGIT_SEGMENTS:
                valid_b = False
                break
            digits_b.append(ch)
        if not valid_b:
            continue

        # Both frames decoded to digits. Check temperatures.
        # Try all 6 orderings of 3 digit positions to display order
        for d_order in permutations(range(3)):
            temp_a_str = ''.join(digits_a[i] for i in d_order)
            temp_b_str = ''.join(digits_b[i] for i in d_order)

            try:
                temp_a = int(temp_a_str)
                temp_b = int(temp_b_str)
            except ValueError:
                continue

            # Valid temperature range for hot tub: 80-106°F
            if 80 <= temp_a <= 106 and 80 <= temp_b <= 106:
                # Only byte 3 changed, so exactly one digit should differ
                diff_count = sum(1 for a, b in zip(digits_a, digits_b) if a != b)
                if diff_count == 1:
                    # Temperature changed by a reasonable amount
                    if abs(temp_a - temp_b) <= 10:
                        results.append({
                            'positions': digit_positions,
                            'display_order': d_order,
                            'temp_a': temp_a,
                            'temp_b': temp_b,
                            'digits_a': digits_a,
                            'digits_b': digits_b,
                            'non_digit_chars': {
                                pos: byte_chars[FRAME_A[pos]]
                                for pos in range(8) if pos not in digit_positions
                            }
                        })

    return results


print("Brute-forcing 7-segment mapping...")
print(f"Testing {5040} segment permutations x digit position combos...")
print()

all_solutions = []
bit_positions = list(range(7))  # bits 0-6 for segments a-g

for perm in permutations(bit_positions):
    mapping = dict(zip(SEGMENTS, perm))
    results = try_mapping(mapping)
    if results:
        for r in results:
            all_solutions.append((mapping.copy(), r))

print(f"Found {len(all_solutions)} solutions\n")

# Group by temperature pair (most useful grouping)
from collections import defaultdict
by_temps = defaultdict(list)
for mapping, result in all_solutions:
    key = (result['temp_a'], result['temp_b'])
    by_temps[key].append((mapping, result))

print("=" * 70)
print("SOLUTIONS GROUPED BY TEMPERATURE PAIR")
print("=" * 70)

for (ta, tb), solutions in sorted(by_temps.items()):
    print(f"\n--- Temperature: {ta}°F <-> {tb}°F ({len(solutions)} mappings) ---")

    # Show first few solutions
    for i, (mapping, result) in enumerate(solutions[:3]):
        pos = result['positions']
        order = result['display_order']
        print(f"  Mapping: {mapping}")
        print(f"  Digit byte positions: {pos}")
        print(f"  Display order (pos->digit): {[pos[j] for j in order]}")
        print(f"  Frame A digits: {''.join(result['digits_a'])} -> {ta}")
        print(f"  Frame B digits: {''.join(result['digits_b'])} -> {tb}")

        # Show all byte decodings
        print(f"  Full byte decode (Frame A):")
        for idx in range(8):
            bv = FRAME_A[idx]
            lower7 = bv & 0x7F
            segs = byte_to_segments(lower7, mapping)
            ch = segments_to_char(segs)
            dp = "dp+" if bv & 0x80 else ""
            role = "DIGIT" if idx in pos else "ctrl/LED"
            print(f"    [{idx}] 0x{bv:02X} = {dp}{ch or '???'} ({role}) segs={set(segs) if segs else '{}'}")

        # Also decode temp-change frames
        print(f"  Temp Down frame decode:")
        for idx in range(8):
            bv = FRAME_TEMP_DOWN[idx]
            lower7 = bv & 0x7F
            segs = byte_to_segments(lower7, mapping)
            ch = segments_to_char(segs)
            dp = "dp+" if bv & 0x80 else ""
            print(f"    [{idx}] 0x{bv:02X} = {dp}{ch or '???'} segs={set(segs) if segs else '{}'}")

        print(f"  Temp Up frame decode:")
        for idx in range(8):
            bv = FRAME_TEMP_UP[idx]
            lower7 = bv & 0x7F
            segs = byte_to_segments(lower7, mapping)
            ch = segments_to_char(segs)
            dp = "dp+" if bv & 0x80 else ""
            print(f"    [{idx}] 0x{bv:02X} = {dp}{ch or '???'} segs={set(segs) if segs else '{}'}")

        # Decode "OH" bytes from logic analyzer
        oh_bytes = [0xE6, 0xE6, 0x06]
        print(f"  OH display decode (from logic analyzer, may have errors):")
        for idx, bv in enumerate(oh_bytes):
            lower7 = bv & 0x7F
            segs = byte_to_segments(lower7, mapping)
            ch = segments_to_char(segs)
            dp = "dp+" if bv & 0x80 else ""
            print(f"    [{idx}] 0x{bv:02X} = {dp}{ch or '???'} segs={set(segs) if segs else '{}'}")

        print()

    if len(solutions) > 3:
        print(f"  ... and {len(solutions) - 3} more solutions with these temperatures")

# Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"Total solutions: {len(all_solutions)}")
print(f"Unique temperature pairs: {list(sorted(by_temps.keys()))}")
print()

# Find solutions where the temp-down frame also produces valid decode
print("Checking solutions against temp-change frames...")
for (ta, tb), solutions in sorted(by_temps.items()):
    for mapping, result in solutions[:1]:  # just check first of each group
        pos = result['positions']
        # Check temp down frame: byte at position 3 changed
        # In temp down, the frame structure might differ
        # Let's just see if the new unique bytes (F3, 03, 18) decode to anything
        for bv in [0xF3, 0x03, 0x18]:
            lower7 = bv & 0x7F
            segs = byte_to_segments(lower7, mapping)
            ch = segments_to_char(segs)
            dp = "dp+" if bv & 0x80 else ""
            if ch and ch in DIGIT_SEGMENTS:
                print(f"  Temps {ta}/{tb}: 0x{bv:02X} = {dp}{ch}")
            else:
                print(f"  Temps {ta}/{tb}: 0x{bv:02X} = {dp}{ch or 'UNKNOWN'} (segs={set(segs)})")
