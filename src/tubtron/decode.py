"""7-segment byte-to-character decoder for VS300FL4 display stream.

Encoding reference: MagnusPer/Balboa-GS510SZ (GS510SZ + VL801D).
Segment mapping: bit6=a, bit5=b, bit4=c, bit3=d, bit2=e, bit1=f, bit0=g.
Bit 7 is the decimal point (dp) and is masked before lookup.

Confirmed mappings (verified against captured data):
  0x30 = "1", 0x70 = "7", 0x00 = " " (blank)

Unverified mappings are derived from the GS510SZ reference and will be
finalized after the temperature ladder capture session.
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
# GS510SZ reference encoding (7-bit, dp masked off):
#   0: a,b,c,d,e,f    = 0x7E
#   1: b,c             = 0x30
#   2: a,b,d,e,g       = 0x6D
#   3: a,b,c,d,g       = 0x79
#   4: b,c,f,g         = 0x33
#   5: a,c,d,f,g       = 0x5B
#   6: a,c,d,e,f,g     = 0x5F
#   7: a,b,c            = 0x70
#   8: a,b,c,d,e,f,g   = 0x7F
#   9: a,b,c,d,f,g     = 0x7B

# Entries verified against VS300FL4 captured data
_CONFIRMED_KEYS = frozenset([0x30, 0x70, 0x00])

# Full lookup table: masked 7-bit value -> character
# Confirmed entries are verified; unverified entries from GS510SZ reference
SEVEN_SEG_TABLE: dict[int, str] = {
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
    0x00: " ",  # blank / off
    # Common non-digit patterns
    0x37: "H",  # b,c,e,f,g (H segments)
    0x0E: "L",  # d,e,f
    0x67: "P",  # a,b,e,f,g
    0x4F: "E",  # a,d,e,f,g
    0x01: "-",  # g only
    0x03: "-",  # g,f -- alternate dash encoding seen in captures
    0x0D: "c",  # d,e,g (lowercase c)
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
