"""Display state machine for VS300FL4 display stream.

Classifies the decoded display string and manages temperature persistence.
Implements the "dumb decoder" principle: reports display state faithfully
without interpreting setpoint flashes, filter cycles, or other business logic.
All interpretation lives in Home Assistant.

Display states:
  - "temperature": Display shows a numeric temperature value
  - "OH": Overheat condition displayed
  - "ICE": Freeze protection displayed
  - "startup": Startup dashes ("--") displayed
  - "blank": Display is blank/off
  - "unknown": Unrecognized display content
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Temperature range for normal confidence (Fahrenheit)
_TEMP_MIN = 80
_TEMP_MAX = 120

# Known non-temperature display patterns
_KNOWN_STATES: dict[str, str] = {
    "OH": "OH",
    "ICE": "ICE",
    "--": "startup",
    "---": "startup",
}

# Pattern for numeric temperature strings (2-3 digits)
_TEMP_PATTERN = re.compile(r"^\d{2,3}$")


@dataclass
class DisplayState:
    """Tracks the current display state and last valid temperature.

    Attributes:
        temperature: Last valid temperature reading (None if no valid reading yet).
        display_state: Current classification of what the display is showing.
        display_string: The raw decoded display string.
        confidence: Confidence in the current temperature reading
                    ("normal", "low", or "none").
    """

    temperature: float | None = None
    display_state: str = "unknown"
    display_string: str = ""
    confidence: str = "none"


def update_display(state: DisplayState, display_str: str) -> DisplayState:
    """Update the display state with a new display string.

    Classifies the display string and updates temperature if it's a valid
    numeric value. Non-temperature displays (OH, ICE, --) preserve the
    last valid temperature.

    This is a pure function that returns a new DisplayState. The previous
    state is used only to carry forward the last valid temperature.

    Args:
        state: Current display state (carries last valid temperature).
        display_str: New decoded display string from the frame parser.

    Returns:
        New DisplayState reflecting the updated display.
    """
    stripped = display_str.strip()

    # Check for blank display
    if not stripped:
        return DisplayState(
            temperature=state.temperature,
            display_state="blank",
            display_string=display_str,
            confidence=state.confidence if state.temperature is not None else "none",
        )

    # Check for known non-temperature states
    if stripped in _KNOWN_STATES:
        return DisplayState(
            temperature=state.temperature,
            display_state=_KNOWN_STATES[stripped],
            display_string=display_str,
            confidence=state.confidence if state.temperature is not None else "none",
        )

    # Check for numeric temperature
    if _TEMP_PATTERN.match(stripped):
        temp_value = float(stripped)
        confidence = (
            "normal" if _TEMP_MIN <= temp_value <= _TEMP_MAX else "low"
        )
        return DisplayState(
            temperature=temp_value,
            display_state="temperature",
            display_string=display_str,
            confidence=confidence,
        )

    # Unknown display content
    return DisplayState(
        temperature=state.temperature,
        display_state="unknown",
        display_string=display_str,
        confidence=state.confidence if state.temperature is not None else "none",
    )
