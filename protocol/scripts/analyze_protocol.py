"""
Re-analyze all capture data with the multiplexing protocol model.

Key insight: Pin 5 and Pin 6 are synchronized at 60Hz.
Pin 6 fires first (digit select), Pin 5 fires ~400us later (segment data).
Both streams send all digits per cycle (frame-based, not per-digit multiplexing).

Pin 6 frame: [77 E6 E6] x3 + [FF]  (10 bytes)
Pin 5 frame: [FE 06 70 XX] [00 06 70 00]  (8 bytes, two 4-byte sub-frames)

This script tries every possible 7-segment bit mapping against ALL known byte
values from ALL captures to find the mapping that makes the most sense.
"""

from itertools import permutations, combinations

SEGMENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g']

# Standard 7-segment patterns
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

LETTER_SEGMENTS = {
    'O': frozenset('abcdef'),  # same as 0
    'H': frozenset('bcefg'),
    'P': frozenset('abefg'),
    'r': frozenset('eg'),
    'E': frozenset('adefg'),
    'F': frozenset('aefg'),
    'C': frozenset('adef'),
    'A': frozenset('abcefg'),
    'L': frozenset('def'),
    'n': frozenset('ceg'),
    'b': frozenset('cdefg'),
    'd': frozenset('bcdeg'),
    '-': frozenset('g'),
    ' ': frozenset(),
}

ALL_CHARS = {}
ALL_CHARS.update(DIGIT_SEGMENTS)
ALL_CHARS.update(LETTER_SEGMENTS)

# ============================================================
# ALL known byte values from ALL captures
# ============================================================

# Pin 5 idle frames (RS-485 adapter, reliable)
PIN5_IDLE_A = [0xFE, 0x06, 0x70, 0x30, 0x00, 0x06, 0x70, 0x00]  # hex.txt
PIN5_IDLE_B = [0xFE, 0x06, 0x70, 0xE6, 0x00, 0x06, 0x70, 0x00]  # rs485_jets.txt

# Pin 5 button-press burst (hex.txt)
PIN5_BURST = [0xE6, 0x77, 0x30, 0xE6, 0x77, 0xE6, 0xE6, 0x77, 0xE6, 0xE0, 0xFF]

# Pin 5 temp-change frames (from original capture, now lost but noted)
PIN5_TEMP_DOWN = [0x06, 0x70, 0xE6, 0x00, 0x00, 0x06, 0x00, 0xF3]
PIN5_TEMP_UP   = [0x06, 0x70, 0xE6, 0x00, 0x00, 0x03, 0x18, 0x00]

# Pin 6 refresh stream (rs485_capture.txt)
PIN6_REFRESH = [0x77, 0xE6, 0xE6, 0x77, 0xE6, 0xE6, 0x77, 0xE6, 0xE6, 0xFF]

# All unique byte values across all captures
ALL_BYTES = sorted(set(
    PIN5_IDLE_A + PIN5_IDLE_B + PIN5_BURST +
    PIN5_TEMP_DOWN + PIN5_TEMP_UP + PIN6_REFRESH
))

print("All unique byte values across captures:")
print("  " + " ".join(f"0x{b:02X}" for b in ALL_BYTES))
print(f"  ({len(ALL_BYTES)} unique values)")
print()

# ============================================================
# Test shifted MagnusPer mapping: bit7=g, bit6=a..bit1=f, bit0=dp
# ============================================================

def decode_byte(byte_val, mapping):
    """Decode a byte using a segment-to-bit mapping. Returns (char, dp_bit, active_segments)."""
    active = set()
    for seg, bit in mapping.items():
        if byte_val & (1 << bit):
            active.add(seg)
    active = frozenset(active)

    # Check dp bit (the one not in mapping)
    all_bits = set(range(8))
    seg_bits = set(mapping.values())
    dp_bits = all_bits - seg_bits
    dp_val = False
    if dp_bits:
        dp_bit = dp_bits.pop()
        dp_val = bool(byte_val & (1 << dp_bit))

    # Look up character
    char = None
    for ch, segs in ALL_CHARS.items():
        if segs == active:
            char = ch
            break

    return char, dp_val, active


def test_mapping(name, mapping):
    """Test a specific mapping against all known data."""
    print(f"\n{'='*70}")
    print(f"MAPPING: {name}")
    print(f"  {mapping}")
    dp_bits = set(range(8)) - set(mapping.values())
    if dp_bits:
        print(f"  Non-segment bit(s): {dp_bits} (dp/indicator)")
    print(f"{'='*70}")

    # Decode all unique bytes
    print(f"\n  All unique byte decodes:")
    for bv in ALL_BYTES:
        ch, dp, segs = decode_byte(bv, mapping)
        dp_str = " +dp" if dp else ""
        seg_str = ",".join(sorted(segs)) if segs else "(none)"
        ch_str = f"'{ch}'" if ch else "???"
        print(f"    0x{bv:02X} = {ch_str:5s} segments={seg_str}{dp_str}")

    # Decode Pin 5 idle frames
    print(f"\n  Pin 5 idle frame A (hex.txt):")
    for i, bv in enumerate(PIN5_IDLE_A):
        ch, dp, segs = decode_byte(bv, mapping)
        print(f"    [{i}] 0x{bv:02X} = {ch or '???'}")

    print(f"\n  Pin 5 idle frame B (rs485_jets.txt):")
    for i, bv in enumerate(PIN5_IDLE_B):
        ch, dp, segs = decode_byte(bv, mapping)
        print(f"    [{i}] 0x{bv:02X} = {ch or '???'}")

    # Decode with sub-frame model
    print(f"\n  Sub-frame model (4+4):")
    for label, frame in [("Frame A", PIN5_IDLE_A), ("Frame B", PIN5_IDLE_B)]:
        sf1 = frame[:4]
        sf2 = frame[4:]
        d1 = [decode_byte(b, mapping) for b in sf1]
        d2 = [decode_byte(b, mapping) for b in sf2]
        chars1 = "".join(c[0] or '?' for c in d1)
        chars2 = "".join(c[0] or '?' for c in d2)
        print(f"    {label}: [{chars1}] [{chars2}]")

    # Decode button-press burst
    print(f"\n  Pin 5 burst (11 bytes):")
    for i, bv in enumerate(PIN5_BURST):
        ch, dp, segs = decode_byte(bv, mapping)
        print(f"    [{i}] 0x{bv:02X} = {ch or '???'}")

    # Decode temp-change frames
    for label, frame in [("Temp Down", PIN5_TEMP_DOWN), ("Temp Up", PIN5_TEMP_UP)]:
        print(f"\n  {label} frame:")
        for i, bv in enumerate(frame):
            ch, dp, segs = decode_byte(bv, mapping)
            print(f"    [{i}] 0x{bv:02X} = {ch or '???'}")

    # Decode Pin 6
    print(f"\n  Pin 6 refresh frame:")
    for i, bv in enumerate(PIN6_REFRESH):
        ch, dp, segs = decode_byte(bv, mapping)
        print(f"    [{i}] 0x{bv:02X} = {ch or '???'}")

    # Try to interpret as temperature
    print(f"\n  Temperature interpretation:")
    # Check bytes 0 and 3 as digit positions (brute-force best result)
    for pos_label, positions in [
        ("bytes [0,3]", (0, 3)),
        ("bytes [0,1]", (0, 1)),
        ("bytes [0,2]", (0, 2)),
        ("bytes [1,3]", (1, 3)),
        ("bytes [2,3]", (2, 3)),
        ("bytes [0,1,2]", (0, 1, 2)),
        ("bytes [0,1,3]", (0, 1, 3)),
        ("bytes [0,2,3]", (0, 2, 3)),
        ("bytes [1,2,3]", (1, 2, 3)),
    ]:
        digits_a = []
        digits_b = []
        valid = True
        for p in positions:
            ca, _, _ = decode_byte(PIN5_IDLE_A[p], mapping)
            cb, _, _ = decode_byte(PIN5_IDLE_B[p], mapping)
            if ca is None or ca not in DIGIT_SEGMENTS or cb is None or cb not in DIGIT_SEGMENTS:
                valid = False
                break
            digits_a.append(ca)
            digits_b.append(cb)
        if valid:
            ta = "".join(digits_a)
            tb = "".join(digits_b)
            print(f"    {pos_label}: Frame A = {ta}, Frame B = {tb}")


# ============================================================
# Test specific candidate mappings
# ============================================================

# 1. MagnusPer standard: bit6=a, bit5=b, bit4=c, bit3=d, bit2=e, bit1=f, bit0=g
magnusper = {'a': 6, 'b': 5, 'c': 4, 'd': 3, 'e': 2, 'f': 1, 'g': 0}
test_mapping("MagnusPer (bit7=dp)", magnusper)

# 2. Shifted MagnusPer: bit7=g, bit6=a, bit5=b, bit4=c, bit3=d, bit2=e, bit1=f
shifted = {'a': 6, 'b': 5, 'c': 4, 'd': 3, 'e': 2, 'f': 1, 'g': 7}
test_mapping("Shifted MagnusPer (bit7=g, bit0=dp)", shifted)

# 3. What if bit7=a? bit7=a, bit6=b, bit5=c, bit4=d, bit3=e, bit2=f, bit1=g
bit7a = {'a': 7, 'b': 6, 'c': 5, 'd': 4, 'e': 3, 'f': 2, 'g': 1}
test_mapping("bit7=a descending (bit0=dp)", bit7a)

# 4. Reversed: bit0=a, bit1=b, ... bit6=g
reversed_map = {'a': 0, 'b': 1, 'c': 2, 'd': 3, 'e': 4, 'f': 5, 'g': 6}
test_mapping("Reversed (bit0=a, bit7=dp)", reversed_map)

# ============================================================
# Now do exhaustive search for mappings where the most bytes decode
# ============================================================

print(f"\n\n{'='*70}")
print("EXHAUSTIVE SEARCH: Best mappings by decode coverage")
print(f"{'='*70}")

# For each of 8 possible dp bit positions, try all 7! permutations
best_results = []

for dp_bit in range(8):
    seg_bits = [b for b in range(8) if b != dp_bit]
    for perm in permutations(seg_bits):
        mapping = dict(zip(SEGMENTS, perm))

        # Score: how many of the ALL_BYTES decode to a known character?
        decoded = 0
        digits = 0
        for bv in ALL_BYTES:
            ch, _, _ = decode_byte(bv, mapping)
            if ch is not None:
                decoded += 1
                if ch in DIGIT_SEGMENTS:
                    digits += 1

        # Also check: do both idle frames produce valid temperature readings?
        # (byte 3 must decode to different digits in frame A vs B)
        ch_a3, _, _ = decode_byte(0x30, mapping)
        ch_b3, _, _ = decode_byte(0xE6, mapping)
        temp_valid = (ch_a3 is not None and ch_a3 in DIGIT_SEGMENTS and
                      ch_b3 is not None and ch_b3 in DIGIT_SEGMENTS and
                      ch_a3 != ch_b3)

        # Check if FE decodes to a digit (likely "8")
        ch_fe, _, _ = decode_byte(0xFE, mapping)
        fe_is_8 = (ch_fe == '8')

        # Check if 70 and 06 decode to anything
        ch_70, _, _ = decode_byte(0x70, mapping)
        ch_06, _, _ = decode_byte(0x06, mapping)

        score = decoded * 10 + digits * 5 + (50 if temp_valid else 0) + (30 if fe_is_8 else 0)

        if score >= 100:  # reasonable threshold
            best_results.append((score, dp_bit, perm, mapping, decoded, digits,
                                temp_valid, fe_is_8, ch_a3, ch_b3, ch_fe, ch_70, ch_06))

# Sort by score descending
best_results.sort(key=lambda x: -x[0])

print(f"\nFound {len(best_results)} mappings with score >= 100")
print(f"Showing top 20:\n")

seen_decodings = set()
for i, (score, dp_bit, perm, mapping, decoded, digits,
        temp_valid, fe_is_8, ch_a3, ch_b3, ch_fe, ch_70, ch_06) in enumerate(best_results[:50]):
    # Deduplicate by what the key bytes decode to
    key = (ch_fe, ch_06, ch_70, ch_a3, ch_b3)
    if key in seen_decodings:
        continue
    seen_decodings.add(key)

    print(f"  #{i+1} Score={score} dp=bit{dp_bit}")
    print(f"    FE={ch_fe or '?'} 06={ch_06 or '?'} 70={ch_70 or '?'} "
          f"30={ch_a3 or '?'} E6={ch_b3 or '?'}")
    print(f"    {decoded}/{len(ALL_BYTES)} bytes decode, {digits} are digits, "
          f"temp_valid={temp_valid}, FE=8:{fe_is_8}")
    print(f"    mapping: {mapping}")

    if len(seen_decodings) >= 20:
        break

# ============================================================
# For the top result, do full decode
# ============================================================
if best_results:
    print(f"\n\n{'='*70}")
    print("DETAILED DECODE OF TOP RESULT")
    print(f"{'='*70}")
    top = best_results[0]
    test_mapping(f"Top result (score={top[0]}, dp=bit{top[1]})", top[3])
