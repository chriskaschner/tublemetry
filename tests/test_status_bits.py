"""Python mirrors of the C++ status bit extraction logic.

Tests verify that the three bit-extraction formulas implemented in
tublemetry_display.cpp produce correct results:

  Heater: (p1_full >> 2) & 0x01  -- bit 2 of the hundreds digit byte
  Pump:   (status   >> 2) & 0x01  -- bit 2 of the 3-bit status nibble
  Light:  (status   >> 1) & 0x01  -- bit 1 of the 3-bit status nibble

Frame layout (24-bit, MSB-first):
  [digit1:7][digit2:7][digit3:7][status:3]

Checksum gate (from process_frame_() scoped block):
  CHECKSUM_MASK = 0x4B  (bits 6, 3, 1, 0)
  Frame is dropped if (p1 & 0x4B) != 0  OR  (status & 0x01) != 0

The status bit 0 is therefore the checksum sentinel -- any frame with
bit 0 of status set is discarded before the binary sensor extraction runs.
"""

import pytest

from tests.test_mock_frames import digits_to_frame, frame_to_digits


# ---------------------------------------------------------------------------
# Python mirrors of C++ bit-extraction
# ---------------------------------------------------------------------------

CHECKSUM_MASK = 0x4B  # same constant as C++ CHECKSUM_MASK


def extract_bits(frame_bits: int) -> tuple[bool, bool, bool]:
    """Extract heater, pump, light from a 24-bit frame.

    Mirrors the logic in TublemetryDisplay::process_frame_() after
    classify_display_state_() returns.

    Returns:
        (heater_on, pump_on, light_on) booleans
    """
    p1 = (frame_bits >> 17) & 0x7F   # hundreds digit byte (p1_full)
    status = frame_bits & 0x07        # 3-bit status nibble
    heater_on = bool((p1 >> 2) & 0x01)
    pump_on   = bool((status >> 2) & 0x01)
    light_on  = bool((status >> 1) & 0x01)
    return heater_on, pump_on, light_on


def passes_checksum(frame_bits: int) -> bool:
    """Return True if the frame passes the C++ checksum gate."""
    p1 = (frame_bits >> 17) & 0x7F
    status = frame_bits & 0x07
    return (p1 & CHECKSUM_MASK) == 0x00 and (status & 0x01) == 0x00


# ---------------------------------------------------------------------------
# TestStatusBitExtraction -- individual bit verify
# ---------------------------------------------------------------------------

class TestStatusBitExtraction:
    """Verify each bit independently — heater, pump, light on and off."""

    # ---- Heater ----

    def test_heater_on_when_p1_bit2_set(self):
        """p1=0x04 (bit 2 set) → heater_on=True."""
        # 0x04 & CHECKSUM_MASK (0x4B) = 0x00 → passes checksum
        frame = digits_to_frame(0x04, 0x00, 0x00, status=0)
        heater, pump, light = extract_bits(frame)
        assert heater is True
        assert pump is False
        assert light is False

    def test_heater_off_when_p1_bit2_clear(self):
        """p1=0x00 → heater_on=False."""
        frame = digits_to_frame(0x00, 0x00, 0x00, status=0)
        heater, pump, light = extract_bits(frame)
        assert heater is False

    def test_heater_on_with_temperature_digit(self):
        """Heater bit survives a real temperature frame: p1=0x34 (0x30 | 0x04 = '1' + bit2)."""
        # 0x30 = '1' digit, OR with 0x04 to set bit 2; 0x34 & 0x4B = 0x00 → checksum passes
        frame = digits_to_frame(0x34, 0x7E, 0x5B, status=0)
        heater, _, _ = extract_bits(frame)
        assert heater is True

    # ---- Pump ----

    def test_pump_on_when_status_bit2_set(self):
        """status=0b100 (bit 2 set) → pump_on=True."""
        frame = digits_to_frame(0x00, 0x00, 0x00, status=0b100)
        _, pump, _ = extract_bits(frame)
        assert pump is True

    def test_pump_off_when_status_bit2_clear(self):
        """status=0b000 → pump_on=False."""
        frame = digits_to_frame(0x00, 0x00, 0x00, status=0b000)
        _, pump, _ = extract_bits(frame)
        assert pump is False

    def test_pump_not_set_by_light_bit(self):
        """status=0b010 (only bit 1) → pump_on=False."""
        frame = digits_to_frame(0x00, 0x00, 0x00, status=0b010)
        _, pump, _ = extract_bits(frame)
        assert pump is False

    # ---- Light ----

    def test_light_on_when_status_bit1_set(self):
        """status=0b010 (bit 1 set) → light_on=True."""
        frame = digits_to_frame(0x00, 0x00, 0x00, status=0b010)
        _, _, light = extract_bits(frame)
        assert light is True

    def test_light_off_when_status_bit1_clear(self):
        """status=0b000 → light_on=False."""
        frame = digits_to_frame(0x00, 0x00, 0x00, status=0b000)
        _, _, light = extract_bits(frame)
        assert light is False

    def test_light_not_set_by_pump_bit(self):
        """status=0b100 (only bit 2) → light_on=False."""
        frame = digits_to_frame(0x00, 0x00, 0x00, status=0b100)
        _, _, light = extract_bits(frame)
        assert light is False


# ---------------------------------------------------------------------------
# TestStatusBitCombinations -- exhaustive 3-bit coverage
# ---------------------------------------------------------------------------

class TestStatusBitCombinations:
    """All 8 status combinations (0-7) extract heater/pump/light cleanly.

    Heater is driven by p1 bit 2 (not status), so it is fixed to 0
    for these tests (p1=0x00). Status bits 2-1 drive pump and light.
    Status bit 0 is the checksum sentinel — combinations 1, 3, 5, 7
    would normally be dropped by the firmware gate, but the extraction
    arithmetic still works correctly on them.
    """

    @pytest.mark.parametrize("status_bits, expected_pump, expected_light", [
        (0b000, False, False),  # nothing on
        (0b001, False, False),  # bit 0 only (checksum sentinel — pump/light still 0)
        (0b010, False, True),   # light on
        (0b011, False, True),   # light on + sentinel bit
        (0b100, True,  False),  # pump on
        (0b101, True,  False),  # pump on + sentinel bit
        (0b110, True,  True),   # pump + light on
        (0b111, True,  True),   # pump + light + sentinel bit
    ])
    def test_all_status_combinations(self, status_bits, expected_pump, expected_light):
        frame = digits_to_frame(0x00, 0x00, 0x00, status=status_bits)
        _, pump, light = extract_bits(frame)
        assert pump == expected_pump, (
            f"status=0b{status_bits:03b}: pump expected {expected_pump}, got {pump}"
        )
        assert light == expected_light, (
            f"status=0b{status_bits:03b}: light expected {expected_light}, got {light}"
        )

    def test_heater_independent_of_status(self):
        """Heater bit is in p1, not status — all 8 status values give same heater result."""
        frame_heater_on  = digits_to_frame(0x04, 0x00, 0x00, status=0b110)
        frame_heater_off = digits_to_frame(0x00, 0x00, 0x00, status=0b110)
        heater_on, _, _ = extract_bits(frame_heater_on)
        heater_off, _, _ = extract_bits(frame_heater_off)
        assert heater_on is True
        assert heater_off is False

    def test_all_three_on_simultaneously(self):
        """Heater=p1 bit 2 set, pump=status bit 2, light=status bit 1 all on."""
        frame = digits_to_frame(0x04, 0x00, 0x00, status=0b110)
        heater, pump, light = extract_bits(frame)
        assert heater is True
        assert pump is True
        assert light is True

    def test_all_three_off_simultaneously(self):
        """All three off: p1 bit 2 clear, status bits 2 and 1 clear."""
        frame = digits_to_frame(0x00, 0x00, 0x00, status=0b000)
        heater, pump, light = extract_bits(frame)
        assert heater is False
        assert pump is False
        assert light is False


# ---------------------------------------------------------------------------
# TestChecksumCompatibility -- status bits don't break the checksum gate
# ---------------------------------------------------------------------------

class TestChecksumCompatibility:
    """Frames with pump/light bits set pass the checksum; status bit 0 fails it."""

    def test_pump_bit_passes_checksum(self):
        """status=0b100: bit 0 = 0 → passes checksum gate."""
        frame = digits_to_frame(0x00, 0x00, 0x00, status=0b100)
        assert passes_checksum(frame) is True

    def test_light_bit_passes_checksum(self):
        """status=0b010: bit 0 = 0 → passes checksum gate."""
        frame = digits_to_frame(0x00, 0x00, 0x00, status=0b010)
        assert passes_checksum(frame) is True

    def test_pump_and_light_passes_checksum(self):
        """status=0b110: bit 0 = 0 → passes checksum gate."""
        frame = digits_to_frame(0x00, 0x00, 0x00, status=0b110)
        assert passes_checksum(frame) is True

    def test_status_bit0_fails_checksum(self):
        """status=0b001: bit 0 = 1 → fails checksum gate (sentinel)."""
        frame = digits_to_frame(0x00, 0x00, 0x00, status=0b001)
        assert passes_checksum(frame) is False

    def test_heater_p1_0x04_passes_checksum(self):
        """p1=0x04: 0x04 & 0x4B = 0x00 → passes checksum gate."""
        frame = digits_to_frame(0x04, 0x00, 0x00, status=0)
        assert passes_checksum(frame) is True

    def test_heater_and_pump_and_light_all_pass(self):
        """p1=0x04, status=0b110: heater + pump + light all-on frame passes checksum."""
        frame = digits_to_frame(0x04, 0x00, 0x00, status=0b110)
        assert passes_checksum(frame) is True

    def test_temperature_frame_with_heater_passes_checksum(self):
        """Real temperature frame with heater bit still passes checksum.

        p1=0x34 (0x30='1' | 0x04=heater); 0x34 & 0x4B = 0x00 → passes.
        """
        frame = digits_to_frame(0x34, 0x7E, 0x5B, status=0)
        assert passes_checksum(frame) is True

    def test_bad_p1_fails_checksum(self):
        """p1=0x7F: 0x7F & 0x4B = 0x4B ≠ 0 → fails checksum gate."""
        frame = digits_to_frame(0x7F, 0x00, 0x00, status=0)
        assert passes_checksum(frame) is False


# ---------------------------------------------------------------------------
# TestPublishOnChange -- Python mirror of C++ change-detection logic
# ---------------------------------------------------------------------------

class TestPublishOnChange:
    """Verify publish-on-change semantics mirror the C++ last_heater_/last_pump_/last_light_ logic.

    C++ pattern:
        int8_t last_heater_{-1};   // -1 forces publish on first frame
        if (static_cast<int8_t>(heater_on) != this->last_heater_) {
            this->last_heater_ = static_cast<int8_t>(heater_on);
            publish_state(heater_on);
        }

    Python simulation:
        last_state = -1  (int8_t initial value)
        if int8(new_state) != last_state:
            last_state = int8(new_state)
            publish(new_state)
    """

    def _simulate_publish(self, initial_last: int, values: list[bool]) -> list[bool]:
        """Simulate the C++ publish-on-change loop, returning published values."""
        published = []
        last = initial_last
        for v in values:
            new_last = 1 if v else 0
            if new_last != last:
                last = new_last
                published.append(v)
        return published

    def test_first_frame_always_publishes(self):
        """last=-1: first frame (True or False) always triggers a publish."""
        assert self._simulate_publish(-1, [True])  == [True]
        assert self._simulate_publish(-1, [False]) == [False]

    def test_same_value_twice_does_not_republish(self):
        """Two identical values in a row → only one publish."""
        published = self._simulate_publish(-1, [True, True])
        assert published == [True]

    def test_same_false_twice_does_not_republish(self):
        """False → False: only one publish."""
        published = self._simulate_publish(-1, [False, False])
        assert published == [False]

    def test_transition_true_to_false_publishes(self):
        """True → False: both publish."""
        published = self._simulate_publish(-1, [True, False])
        assert published == [True, False]

    def test_transition_false_to_true_publishes(self):
        """False → True: both publish."""
        published = self._simulate_publish(-1, [False, True])
        assert published == [False, True]

    def test_rapid_toggle_publishes_every_change(self):
        """True/False/True/False → all 4 publish."""
        published = self._simulate_publish(-1, [True, False, True, False])
        assert published == [True, False, True, False]

    def test_stable_sequence_single_publish(self):
        """True/True/True/True → single publish on first."""
        published = self._simulate_publish(-1, [True, True, True, True])
        assert published == [True]

    def test_independent_state_per_sensor(self):
        """Heater, pump, and light maintain independent last-state tracking."""
        # Each sensor starts at -1; simulate concurrent updates
        values = [
            (True,  False, True),   # frame 1: heater on, pump off, light on
            (True,  False, True),   # frame 2: same — no republish for any
            (False, True,  True),   # frame 3: heater off, pump on, light same
        ]

        last_h, last_p, last_l = -1, -1, -1
        heater_pubs, pump_pubs, light_pubs = [], [], []

        for h, p, l in values:
            for sensor_val, last_ref, pubs in [
                (h, last_h, heater_pubs),
                (p, last_p, pump_pubs),
                (l, last_l, light_pubs),
            ]:
                new_last = 1 if sensor_val else 0
                if new_last != last_ref:
                    pubs.append(sensor_val)
            # Update last references
            last_h = 1 if h else 0
            last_p = 1 if p else 0
            last_l = 1 if l else 0

        assert heater_pubs == [True, False]  # published twice (on/off)
        assert pump_pubs   == [False, True]  # initial False then True
        assert light_pubs  == [True]         # only once (stable after first)
