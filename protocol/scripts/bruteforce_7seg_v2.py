"""
Brute-force 7-segment decoder v2 for Balboa VS300FL4.
Relaxes constraints from v1:
  - Try ALL 8 bit positions for 7 segments (dp can be any bit or absent)
  - Wider temperature range (50-120°F)
  - Allow 2-digit temperatures
  - Try different digit position counts (2 or 3 from bytes 0-3)
  - Check if frame is two 4-byte sub-frames (second is for panel port 2)

Key data:
  Frame A (hex.txt):  FE 06 70 30 00 06 70 00
  Frame B (rs485):    FE 06 70 E6 00 06 70 00
  Only byte 3 changes.
"""
from itertools import permutations, combinations

SEGMENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g']

DIGIT_SEGMENTS = {
    0: frozenset('abcdef'),
    1: frozenset('bc'),
    2: frozenset('abdeg'),
    3: frozenset('abcdg'),
    4: frozenset('bcfg'),
    5: frozenset('acdfg'),
    6: frozenset('acdefg'),
    7: frozenset('abc'),
    8: frozenset('abcdefg'),
    9: frozenset('abcdfg'),
}

# Precompute: for each mapping (tuple of 7 bit positions), build byte-to-digit lookup
# A mapping is a tuple: (bit_for_a, bit_for_b, ..., bit_for_g)

def build_lookup(bit_positions):
    """Given 7 bit positions for segments a-g, build {byte_value: digit} lookup.
    Only considers the 7 relevant bits (other bits can be anything)."""
    lookup = {}
    for digit, segs in DIGIT_SEGMENTS.items():
        val = 0
        for i, seg in enumerate(SEGMENTS):
            if seg in segs:
                val |= (1 << bit_positions[i])
        lookup[val] = digit
    return lookup

# Frame bytes (first 4 = our panel's data)
SUB_A = [0xFE, 0x06, 0x70, 0x30]  # hex.txt
SUB_B = [0xFE, 0x06, 0x70, 0xE6]  # rs485_capture.txt

# Mask to extract only the segment bits
def make_mask(bit_positions):
    mask = 0
    for b in bit_positions:
        mask |= (1 << b)
    return mask

print("Brute-force 7-segment decode v2")
print("Testing P(8,7) = 40320 bit mappings...")
print()

solutions = []
count = 0

# Try all permutations of 7 bit positions chosen from 8 bits
for bit_combo in combinations(range(8), 7):
    for bit_perm in permutations(bit_combo):
        count += 1
        mask = make_mask(bit_perm)
        lookup = build_lookup(bit_perm)

        # Byte 3 changes: both must decode to digits
        val_a3 = SUB_A[3] & mask
        val_b3 = SUB_B[3] & mask

        if val_a3 not in lookup or val_b3 not in lookup:
            continue

        digit_a3 = lookup[val_a3]
        digit_b3 = lookup[val_b3]

        if digit_a3 == digit_b3:
            continue  # digit must have changed

        # Now check which other bytes (0,1,2) decode to digits
        decoded_a = [None] * 4
        decoded_b = [None] * 4
        decoded_a[3] = digit_a3
        decoded_b[3] = digit_b3

        for i in range(3):
            val = SUB_A[i] & mask
            if val in lookup:
                decoded_a[i] = lookup[val]
                decoded_b[i] = lookup[val]  # same byte in both frames

        # Need at least 2 more digits (for 3-digit temp) or 1 more (for 2-digit)
        digit_positions_candidates = [i for i in range(3) if decoded_a[i] is not None]

        # Try 3-digit temperatures
        for extra_pos in combinations(digit_positions_candidates, 2):
            digit_pos = sorted(list(extra_pos) + [3])

            for display_order in permutations(range(3)):
                digits_a = [decoded_a[digit_pos[display_order[j]]] for j in range(3)]
                digits_b = [decoded_b[digit_pos[display_order[j]]] for j in range(3)]

                temp_a = digits_a[0] * 100 + digits_a[1] * 10 + digits_a[2]
                temp_b = digits_b[0] * 100 + digits_b[1] * 10 + digits_b[2]

                if 80 <= temp_a <= 120 and 80 <= temp_b <= 120:
                    diff = abs(temp_a - temp_b)
                    if 1 <= diff <= 10:
                        mapping = dict(zip(SEGMENTS, bit_perm))
                        non_seg_bit = [b for b in range(8) if b not in bit_perm][0]
                        solutions.append({
                            'mapping': mapping,
                            'non_seg_bit': non_seg_bit,
                            'digit_pos': digit_pos,
                            'display_order': display_order,
                            'temp_a': temp_a,
                            'temp_b': temp_b,
                            'bit_perm': bit_perm,
                        })

        # Try 2-digit temperatures
        for extra_pos in digit_positions_candidates:
            digit_pos = sorted([extra_pos, 3])

            for display_order in permutations(range(2)):
                digits_a = [decoded_a[digit_pos[display_order[j]]] for j in range(2)]
                digits_b = [decoded_b[digit_pos[display_order[j]]] for j in range(2)]

                temp_a = digits_a[0] * 10 + digits_a[1]
                temp_b = digits_b[0] * 10 + digits_b[1]

                if 80 <= temp_a <= 120 and 80 <= temp_b <= 120:
                    diff = abs(temp_a - temp_b)
                    if 1 <= diff <= 10:
                        mapping = dict(zip(SEGMENTS, bit_perm))
                        non_seg_bit = [b for b in range(8) if b not in bit_perm][0]
                        solutions.append({
                            'mapping': mapping,
                            'non_seg_bit': non_seg_bit,
                            'digit_pos': digit_pos,
                            'display_order': display_order,
                            'temp_a': temp_a,
                            'temp_b': temp_b,
                            'bit_perm': bit_perm,
                        })

if count % 10000 == 0:
    print(f"  Checked {count} mappings, {len(solutions)} solutions so far...")

print(f"\nChecked {count} total mappings")
print(f"Found {len(solutions)} solutions\n")

# Group and display
from collections import defaultdict
by_temps = defaultdict(list)
for s in solutions:
    by_temps[(s['temp_a'], s['temp_b'])].append(s)

print("=" * 70)
print("SOLUTIONS BY TEMPERATURE")
print("=" * 70)

for (ta, tb), sols in sorted(by_temps.items()):
    print(f"\n{'='*50}")
    print(f"TEMP: {ta}°F <-> {tb}°F  ({len(sols)} mappings found)")
    print(f"{'='*50}")

    # Show first solution in detail
    s = sols[0]
    m = s['mapping']
    non_seg = s['non_seg_bit']
    bit_perm = s['bit_perm']
    mask = make_mask(bit_perm)
    lookup = build_lookup(bit_perm)

    print(f"Segment mapping: {m}")
    print(f"Non-segment bit: bit {non_seg} (dp/indicator)")
    print(f"Digit positions in 4-byte sub-frame: {s['digit_pos']}")
    print(f"Display order: {s['display_order']}")

    # Build full lookup table
    print(f"\n  Full digit table:")
    for d in range(10):
        segs = DIGIT_SEGMENTS[d]
        val = 0
        for i, seg in enumerate(SEGMENTS):
            if seg in segs:
                val |= (1 << bit_perm[i])
        print(f"    '{d}' = 0x{val:02X} ({val:08b})")

    # Decode all unique bytes
    all_bytes = [0xFE, 0x06, 0x70, 0x30, 0xE6, 0x00, 0xF3, 0x03, 0x18]
    print(f"\n  All known byte values decoded:")
    for bv in all_bytes:
        masked = bv & mask
        dp_val = bv & (1 << non_seg)
        dp_str = " +indicator" if dp_val else ""
        if masked in lookup:
            print(f"    0x{bv:02X} = '{lookup[masked]}'{dp_str}")
        else:
            # Show which segments are active
            active = []
            for i, seg in enumerate(SEGMENTS):
                if masked & (1 << bit_perm[i]):
                    active.append(seg)
            print(f"    0x{bv:02X} = NOT A DIGIT (active segments: {active}){dp_str}")

    # Decode OH bytes
    print(f"\n  OH display bytes from logic analyzer (E6 E6 06):")
    for bv in [0xE6, 0xE6, 0x06]:
        masked = bv & mask
        dp_val = bv & (1 << non_seg)
        dp_str = " +indicator" if dp_val else ""
        if masked in lookup:
            print(f"    0x{bv:02X} = '{lookup[masked]}'{dp_str}")
        else:
            active = []
            for i, seg in enumerate(SEGMENTS):
                if masked & (1 << bit_perm[i]):
                    active.append(seg)
            # Also check letters
            for name, letter_segs in [('O','abcdef'),('H','bcefg'),('P','abefg'),
                                       ('r','eg'),('E','adefg'),('F','aefg'),
                                       ('C','adef'),('A','abcefg'),('n','ceg')]:
                letter_set = frozenset(letter_segs)
                if frozenset(active) == letter_set:
                    print(f"    0x{bv:02X} = '{name}'{dp_str} (letter match!)")
                    break
            else:
                print(f"    0x{bv:02X} = NOT A DIGIT (active segments: {active}){dp_str}")

    # Check consistency with temp-change frames
    print(f"\n  Temp-down frame: 06 70 E6 00 | 00 06 00 F3")
    print(f"  Temp-up frame:   06 70 E6 00 | 00 03 18 00")
    print(f"  (These frames appear during button-press display mode)")

    if len(sols) > 1:
        # Check if all solutions have same digit table
        first_perm = sols[0]['bit_perm']
        same_count = sum(1 for s2 in sols if s2['bit_perm'] == first_perm)
        print(f"\n  {same_count}/{len(sols)} solutions use the same bit mapping")
        if same_count < len(sols):
            print(f"  Other bit mappings also produce this temperature pair")
            for s2 in sols[1:4]:
                if s2['bit_perm'] != first_perm:
                    print(f"    Alt mapping: {s2['mapping']}, positions: {s2['digit_pos']}")

print(f"\n\n{'='*70}")
print("OVERALL SUMMARY")
print(f"{'='*70}")
print(f"Total solutions: {len(solutions)}")
print(f"Temperature pairs: {sorted(by_temps.keys())}")
if solutions:
    # Count unique bit mappings
    unique_mappings = set(s['bit_perm'] for s in solutions)
    print(f"Unique segment-to-bit mappings: {len(unique_mappings)}")
