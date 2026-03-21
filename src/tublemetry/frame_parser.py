"""Pin 5 RS-485 frame parser for VS300FL4 display stream.

Parses 8-byte frames from the board-to-panel display content channel.
Each frame is decoded byte-by-byte using the 7-segment lookup table.

Frame structure (idle):
  Byte 0: FE (status marker, present during idle, absent during button press)
  Byte 1: 06 (fixed -- likely LED indicator, not a digit)
  Byte 2: 70 (fixed -- decodes to "7")
  Byte 3: XX (varies with temperature -- the temperature digit)
  Byte 4: 00 (blank)
  Byte 5: 06 (fixed)
  Byte 6: 70 (fixed -- decodes to "7")
  Byte 7: 00 (blank)

Sub-frame model: bytes [0-3] and [4-7] may represent two display zones.
The exact mapping of which bytes are digits vs control bytes will be
refined after the temperature ladder capture.
"""

from dataclasses import dataclass

from tublemetry.decode import decode_7seg


@dataclass(frozen=True)
class FrameResult:
    """Result of parsing a Pin 5 RS-485 display frame.

    Attributes:
        display_string: Concatenated decoded characters from all 8 bytes.
        has_fe_marker: True if byte 0 is 0xFE (idle/status indicator).
        raw_hex: Space-separated uppercase hex representation of the frame.
        digit_values: List of (character, confidence) tuples from decode_7seg.
        sub_frame_1: First 4 bytes (bytes 0-3).
        sub_frame_2: Last 4 bytes (bytes 4-7).
    """

    display_string: str
    has_fe_marker: bool
    raw_hex: str
    digit_values: list[tuple[str, str]]
    sub_frame_1: bytes
    sub_frame_2: bytes


def parse_pin5_frame(data: bytes) -> FrameResult:
    """Parse an 8-byte Pin 5 RS-485 display frame.

    Validates frame length, decodes each byte through the 7-segment
    lookup table, and assembles the result.

    Args:
        data: Raw 8-byte frame from the Pin 5 RS-485 stream.

    Returns:
        FrameResult with decoded display data.

    Raises:
        ValueError: If data is not exactly 8 bytes.
    """
    if len(data) != 8:
        raise ValueError(
            f"Frame must be exactly 8 bytes, got {len(data)}"
        )

    # Detect FE status marker
    has_fe_marker = data[0] == 0xFE

    # Decode each byte
    digit_values = [decode_7seg(b) for b in data]

    # Build display string from decoded characters
    display_string = "".join(char for char, _confidence in digit_values)

    # Raw hex representation
    raw_hex = " ".join(f"{b:02X}" for b in data)

    # Split into sub-frames
    sub_frame_1 = bytes(data[0:4])
    sub_frame_2 = bytes(data[4:8])

    return FrameResult(
        display_string=display_string,
        has_fe_marker=has_fe_marker,
        raw_hex=raw_hex,
        digit_values=digit_values,
        sub_frame_1=sub_frame_1,
        sub_frame_2=sub_frame_2,
    )
