"""
Brute-force 7-segment decoder for 3-digit temperature in 100-109 range.

Key constraint from user: the display shows temperatures like 104, in the 10X range.
This means:
  - 3 digit positions in the frame
  - Hundreds = "1" (constant), Tens = "0" (constant), Ones = varies
  - Byte 3 is the ones digit (only byte that changes between captures)
  - Two of {FE, 06, 70} must decode to "1" and "0"

Sub-frame 1: [FE, 06, 70, XX]  where XX = 0x30 or 0xE6
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

# Bit counts for quick filtering
# "1"=2 segs, "0"=6 segs, "7"=3 segs, "8"=7 segs, etc.
DIGIT_SEG_COUNT = {d: len(s) for d, s in DIGIT_SEGMENTS.items()}

# Frame bytes
FRAME_BYTES = [0xFE, 0x06, 0x70]  # constant bytes (positions 0,1,2)
BYTE_A = 0x30   # ones digit in capture A
BYTE_B = 0xE6   # ones digit in capture B

# Additional known bytes from other frames
OTHER_BYTES = {
    0xF3: "temp-down frame byte 7",
    0x03: "temp-up frame byte 5 / temp-down burst",
    0x18: "temp-up frame byte 6",
    0x77: "burst / Pin 6",
    0xE0: "burst byte 9",
    0xFF: "burst byte 10 / Pin 6 terminator",
    0x00: "blank",
}

print("3-Digit Temperature Brute-Force (10X range)")
print(f"Frame: FE 06 70 XX, XX = 0x{BYTE_A:02X} or 0x{BYTE_B:02X}")
print(f"Testing all P(8,7) = 40,320 mappings × digit position combos")
print()

solutions = []
count = 0

for dp_bit in range(8):
    seg_bits = [b for b in range(8) if b != dp_bit]
    for perm in permutations(seg_bits):
        count += 1
        mapping = dict(zip(SEGMENTS, perm))

        # Build byte-to-digit lookup (using only the 7 segment bits)
        seg_mask = sum(1 << b for b in perm)
        lookup = {}
        for digit, segs in DIGIT_SEGMENTS.items():
            val = 0
            for i, seg in enumerate(SEGMENTS):
                if seg in segs:
                    val |= (1 << perm[i])
            lookup[val] = digit

        # Byte 3 (ones digit) must decode to two different digits
        val_a = BYTE_A & seg_mask
        val_b = BYTE_B & seg_mask
        if val_a not in lookup or val_b not in lookup:
            continue
        digit_a = lookup[val_a]
        digit_b = lookup[val_b]
        if digit_a == digit_b:
            continue

        # Both must be valid ones digits (0-9)
        # For 10X range, ones digit is 0-9

        # Now: two of {FE, 06, 70} must decode to "1" and "0"
        decoded_const = {}
        for bv in FRAME_BYTES:
            val = bv & seg_mask
            if val in lookup:
                decoded_const[bv] = lookup[val]

        # Need exactly "1" and "0" among the constant bytes
        has_one = any(d == 1 for d in decoded_const.values())
        has_zero = any(d == 0 for d in decoded_const.values())

        if not (has_one and has_zero):
            continue

        # Find which bytes are "1" and "0"
        ones_byte = [bv for bv, d in decoded_const.items() if d == 1]
        zeros_byte = [bv for bv, d in decoded_const.items() if d == 0]

        # Try all valid combinations
        for ob in ones_byte:
            for zb in zeros_byte:
                if ob == zb:
                    continue

                # The third constant byte is an indicator/LED
                indicator_byte = [bv for bv in FRAME_BYTES if bv != ob and bv != zb][0]

                # Determine display positions:
                # Need to figure out which position is hundreds, tens, ones
                one_pos = FRAME_BYTES.index(ob)
                zero_pos = FRAME_BYTES.index(zb)
                ind_pos = FRAME_BYTES.index(indicator_byte)

                # Temperature: 100 + ones digit
                temp_a = 100 + digit_a
                temp_b = 100 + digit_b

                # Reasonable check: temps should be in 80-110 range
                if not (80 <= temp_a <= 110 and 80 <= temp_b <= 110):
                    continue

                # Decode ALL other known bytes
                other_decoded = {}
                for bv, desc in OTHER_BYTES.items():
                    val = bv & seg_mask
                    dp_val = bool(bv & (1 << dp_bit))
                    if val in lookup:
                        other_decoded[bv] = (lookup[val], dp_val, desc)
                    else:
                        # Check segment pattern
                        active = []
                        for i, seg in enumerate(SEGMENTS):
                            if val & (1 << perm[i]):
                                active.append(seg)
                        other_decoded[bv] = (None, dp_val, desc, frozenset(active))

                solutions.append({
                    'mapping': dict(mapping),
                    'dp_bit': dp_bit,
                    'temp_a': temp_a,
                    'temp_b': temp_b,
                    'digit_a': digit_a,
                    'digit_b': digit_b,
                    'one_byte': ob,
                    'zero_byte': zb,
                    'indicator_byte': indicator_byte,
                    'one_pos': one_pos,
                    'zero_pos': zero_pos,
                    'perm': perm,
                    'other_decoded': other_decoded,
                    'lookup': lookup,
                    'seg_mask': seg_mask,
                })

print(f"Checked {count} mappings")
print(f"Found {len(solutions)} solutions\n")

# Group by temperature pair
from collections import defaultdict
by_temps = defaultdict(list)
for s in solutions:
    by_temps[(s['temp_a'], s['temp_b'])].append(s)

print("=" * 70)
print("SOLUTIONS BY TEMPERATURE PAIR")
print("=" * 70)

for (ta, tb), sols in sorted(by_temps.items()):
    print(f"\n{'='*60}")
    print(f"  {ta}°F ↔ {tb}°F  ({len(sols)} mappings)")
    print(f"{'='*60}")

    # Group by which bytes are "1" and "0"
    by_assignment = defaultdict(list)
    for s in sols:
        key = (s['one_byte'], s['zero_byte'], s['indicator_byte'])
        by_assignment[key].append(s)

    for (ob, zb, ib), sub_sols in by_assignment.items():
        print(f"\n  '1'=0x{ob:02X} (pos {FRAME_BYTES.index(ob)}), "
              f"'0'=0x{zb:02X} (pos {FRAME_BYTES.index(zb)}), "
              f"indicator=0x{ib:02X} (pos {FRAME_BYTES.index(ib)})")
        print(f"  ({len(sub_sols)} mappings with this byte assignment)")

        # Show first solution detail
        s = sub_sols[0]
        m = s['mapping']
        lookup = s['lookup']
        seg_mask = s['seg_mask']
        dp = s['dp_bit']

        print(f"  dp=bit{dp}, mapping: {m}")

        # Build full digit table
        print(f"\n  Digit table:")
        for d in range(10):
            segs = DIGIT_SEGMENTS[d]
            val = 0
            for i, seg in enumerate(SEGMENTS):
                if seg in segs:
                    val |= (1 << s['perm'][i])
            print(f"    '{d}' = 0x{val:02X} (0x{val | (1<<dp):02X} with dp)")

        # Full frame decode
        print(f"\n  Frame A decode: [FE 06 70 30] [00 06 70 00]")
        for i, bv in enumerate([0xFE, 0x06, 0x70, 0x30, 0x00, 0x06, 0x70, 0x00]):
            val = bv & seg_mask
            dp_val = bool(bv & (1 << dp))
            dp_str = "+dp" if dp_val else ""
            if val in lookup:
                print(f"    [{i}] 0x{bv:02X} = '{lookup[val]}'{dp_str}")
            else:
                active = [seg for j, seg in enumerate(SEGMENTS) if val & (1 << s['perm'][j])]
                print(f"    [{i}] 0x{bv:02X} = ??? (segs: {active}){dp_str}")

        print(f"\n  Frame B decode: [FE 06 70 E6] [00 06 70 00]")
        for i, bv in enumerate([0xFE, 0x06, 0x70, 0xE6, 0x00, 0x06, 0x70, 0x00]):
            val = bv & seg_mask
            dp_val = bool(bv & (1 << dp))
            dp_str = "+dp" if dp_val else ""
            if val in lookup:
                print(f"    [{i}] 0x{bv:02X} = '{lookup[val]}'{dp_str}")
            else:
                active = [seg for j, seg in enumerate(SEGMENTS) if val & (1 << s['perm'][j])]
                print(f"    [{i}] 0x{bv:02X} = ??? (segs: {active}){dp_str}")

        # Temp change frames
        print(f"\n  Temp-down frame: [06 70 E6 00] [00 06 00 F3]")
        for i, bv in enumerate([0x06, 0x70, 0xE6, 0x00, 0x00, 0x06, 0x00, 0xF3]):
            val = bv & seg_mask
            dp_val = bool(bv & (1 << dp))
            dp_str = "+dp" if dp_val else ""
            if val in lookup:
                print(f"    [{i}] 0x{bv:02X} = '{lookup[val]}'{dp_str}")
            else:
                active = [seg for j, seg in enumerate(SEGMENTS) if val & (1 << s['perm'][j])]
                print(f"    [{i}] 0x{bv:02X} = ??? (segs: {active}){dp_str}")

        print(f"\n  Temp-up frame: [06 70 E6 00] [00 03 18 00]")
        for i, bv in enumerate([0x06, 0x70, 0xE6, 0x00, 0x00, 0x03, 0x18, 0x00]):
            val = bv & seg_mask
            dp_val = bool(bv & (1 << dp))
            dp_str = "+dp" if dp_val else ""
            if val in lookup:
                print(f"    [{i}] 0x{bv:02X} = '{lookup[val]}'{dp_str}")
            else:
                active = [seg for j, seg in enumerate(SEGMENTS) if val & (1 << s['perm'][j])]
                print(f"    [{i}] 0x{bv:02X} = ??? (segs: {active}){dp_str}")

        # Burst decode
        print(f"\n  Button burst: E6 77 30 E6 77 E6 E6 77 E6 E0 FF")
        for i, bv in enumerate([0xE6, 0x77, 0x30, 0xE6, 0x77, 0xE6, 0xE6, 0x77, 0xE6, 0xE0, 0xFF]):
            val = bv & seg_mask
            dp_val = bool(bv & (1 << dp))
            dp_str = "+dp" if dp_val else ""
            if val in lookup:
                print(f"    [{i}] 0x{bv:02X} = '{lookup[val]}'{dp_str}")
            else:
                active = [seg for j, seg in enumerate(SEGMENTS) if val & (1 << s['perm'][j])]
                print(f"    [{i}] 0x{bv:02X} = ??? (segs: {active}){dp_str}")

        # Pin 6 decode
        print(f"\n  Pin 6 refresh: 77 E6 E6 77 E6 E6 77 E6 E6 FF")
        for i, bv in enumerate([0x77, 0xE6, 0xE6, 0x77, 0xE6, 0xE6, 0x77, 0xE6, 0xE6, 0xFF]):
            val = bv & seg_mask
            dp_val = bool(bv & (1 << dp))
            dp_str = "+dp" if dp_val else ""
            if val in lookup:
                print(f"    [{i}] 0x{bv:02X} = '{lookup[val]}'{dp_str}")
            else:
                active = [seg for j, seg in enumerate(SEGMENTS) if val & (1 << s['perm'][j])]
                print(f"    [{i}] 0x{bv:02X} = ??? (segs: {active}){dp_str}")

print(f"\n\n{'='*70}")
print("SUMMARY")
print(f"{'='*70}")
print(f"Total solutions: {len(solutions)}")
print(f"Temperature pairs: {sorted(by_temps.keys())}")
if solutions:
    unique_mappings = set(s['perm'] for s in solutions)
    print(f"Unique segment-to-bit mappings: {len(unique_mappings)}")
    unique_assignments = set((s['one_byte'], s['zero_byte']) for s in solutions)
    print(f"Unique '1'/'0' byte assignments: {unique_assignments}")
