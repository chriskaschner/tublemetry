"""Shared test fixtures and known frame data for tubtron tests."""

# Known idle frame at one temperature (FE present = idle state)
# FE 06 70 30 00 06 70 00
IDLE_FRAME_A = bytes([0xFE, 0x06, 0x70, 0x30, 0x00, 0x06, 0x70, 0x00])

# Known idle frame at another temperature (byte 3 differs)
# FE 06 70 E6 00 06 70 00
IDLE_FRAME_B = bytes([0xFE, 0x06, 0x70, 0xE6, 0x00, 0x06, 0x70, 0x00])

# Captured temp-down response (no FE marker)
# 06 70 E6 00 00 06 00 F3
TEMP_DOWN_FRAME = bytes([0x06, 0x70, 0xE6, 0x00, 0x00, 0x06, 0x00, 0xF3])

# Captured temp-up response (no FE marker)
# 06 70 E6 00 00 03 18 00
TEMP_UP_FRAME = bytes([0x06, 0x70, 0xE6, 0x00, 0x00, 0x03, 0x18, 0x00])

# Confirmed byte-to-character mappings from protocol analysis
# These have been verified against captured data and the GS510SZ reference
CONFIRMED_MAPPINGS: dict[int, str] = {
    0x30: "1",
    0x70: "7",
    0x00: " ",
}
