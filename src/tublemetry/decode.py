"""7-segment byte-to-character decoder for VS300FL4 display stream.

Encoding reference: MagnusPer/Balboa-GS510SZ (GS510SZ + VL801D), with
VS300FL4-specific corrections confirmed via logic analyzer ladder capture
(2026-03-20).

Segment mapping: bit6=a, bit5=b, bit4=c, bit3=d, bit2=e, bit1=f, bit0=g.
Bit 7 is the decimal point (dp) and is masked before lookup.

All digit and letter entries below are confirmed against VS300FL4 captured data.
VS300FL4 difference from GS510SZ: "9" = 0x73 (no bottom segment), not 0x7B.
"""

# Segment bits (after masking dp):
#   bit6=a  bit5=b  bit4=c  bit3=d  bit2=e  bit1=f  bit0=g
#
#    aaaa
#   f    b
#   f    b
#    gggg
#   e    c
#   e    c
#    dddd
#
# VS300FL4 confirmed encoding (7-bit, dp masked off):
#   0: a,b,c,d,e,f    = 0x7E
#   1: b,c             = 0x30
#   2: a,b,d,e,g       = 0x6D
#   3: a,b,c,d,g       = 0x79
#   4: b,c,f,g         = 0x33
#   5: a,c,d,f,g       = 0x5B
#   6: a,c,d,e,f,g     = 0x5F
#   7: a,b,c            = 0x70
#   8: a,b,c,d,e,f,g   = 0x7F
#   9: a,b,c,f,g       = 0x73  (NOT 0x7B -- no bottom segment)

# All entries confirmed via VS300FL4 ladder capture 2026-03-20
_CONFIRMED_KEYS = frozenset([
    0x7E, 0x30, 0x6D, 0x79, 0x33, 0x5B, 0x5F, 0x70, 0x7F, 0x73,
    0x00, 0x37, 0x0E, 0x4F, 0x0D, 0x0F,
])

# Full lookup table: masked 7-bit value -> character
SEVEN_SEG_TABLE: dict[int, str] = {
    0x7E: "0",
    0x30: "1",
    0x34: "1",  # setpoint display mode — "1" with lower-left foot (segment e)
    0x6D: "2",
    0x79: "3",
    0x33: "4",
    0x5B: "5",
    0x5F: "6",
    0x70: "7",
    0x7F: "8",
    0x73: "9",
    0x00: " ",  # blank / off
    # Letter patterns (confirmed via mode display captures)
    0x37: "H",  # b,c,e,f,g
    0x0E: "L",  # d,e,f
    0x4F: "E",  # a,d,e,f,g
    0x0D: "c",  # d,e,g (lowercase c)
    0x0F: "t",  # d,e,f,g (lowercase t)
    # Unverified (GS510SZ reference, not yet seen on VS300FL4)
    0x67: "P",  # a,b,e,f,g
    0x01: "-",  # g only
    0x03: "-",  # g,f -- alternate dash encoding
    0x05: "r",  # e,g
    0x1D: "o",  # c,d,e,g (lowercase o)
}


def decode_7seg(byte_val: int) -> tuple[str, str]:
    """Decode a 7-segment byte value to its character representation.

    Masks off bit 7 (decimal point) before lookup. Returns a tuple of
    (character, confidence) where confidence is "confirmed" for entries
    verified against captured VS300FL4 data, or "unverified" for entries
    derived from the GS510SZ reference or unknown bytes.

    Args:
        byte_val: Raw byte value from the RS-485 display stream (0x00-0xFF).

    Returns:
        Tuple of (character, confidence).
        - character: The decoded character, or "?" if not in the lookup table.
        - confidence: "confirmed" if verified, "unverified" otherwise.
    """
    masked = byte_val & 0x7F  # Strip dp bit (bit 7)

    if masked in SEVEN_SEG_TABLE:
        char = SEVEN_SEG_TABLE[masked]
        confidence = "confirmed" if masked in _CONFIRMED_KEYS else "unverified"
        return (char, confidence)

    return ("?", "unverified")
