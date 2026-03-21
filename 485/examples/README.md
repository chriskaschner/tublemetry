# Example Captures

Logic analyzer captures from a Balboa VS300FL4 controller, decoded using
`decode_clockdata_v2.py`. Captures taken with a Saleae Logic clone (fx2lafw)
at 1MHz, 2 channels: D0=Data (Pin 5), D1=Clock (Pin 6).

## Included Files

- `steady_105F.csv` -- 10 frames of steady "105" display (water temp)
- `mode_Ec.csv` -- 10 frames of "Ec" (economy mode) display

## Decoded Examples

### Steady Temperature Display (105F)

```
Frames: 10, Pulses per frame: [24]
All frames: "105"

Frame bits (MSB-first): 011000011111100110011000
  digit 1: 0110000 = 0x30 = "1"
  digit 2: 1111110 = 0x7E = "0"
  digit 3: 1011011 = 0x5B = "5"
  status:  000
```

### Economy Mode Display (Ec)

```
Frames: 10, Pulses per frame: [24]
All frames: " Ec"

Frame bits (MSB-first): 000000010011110000110100
  digit 1: 0000000 = 0x00 = " " (blank)
  digit 2: 1001111 = 0x4F = "E"
  digit 3: 0001101 = 0x0D = "c"
  status:  100
```

### Setpoint Flash (pressing Temp Down from 95 to 90)

During a 10-second capture while pressing Temp Down repeatedly:

```
Frames: 600 total
  "104" x101 frames -- actual water temperature (shown between flashes)
  "   " x248 frames -- display blanked during flash transition
  " 95" x30 frames  -- setpoint flash at 95F
  " 94" x30 frames  -- setpoint flash at 94F
  " 93" x30 frames  -- setpoint flash at 93F
  " 92" x31 frames  -- setpoint flash at 92F
  " 91" x29 frames  -- setpoint flash at 91F
  " 90" x101 frames -- final setpoint at 90F
```

The display alternates between the actual water temperature and the new
setpoint. Blank frames appear during the transition. The setpoint display
format for temperatures under 100F is " XX" (leading space + 2 digits).

### VS300FL4 vs GS510SZ Difference

The only confirmed encoding difference from the GS510SZ reference:

```
Digit "9":
  VS300FL4: 0x73 (1110011) -- segments a,b,c,f,g (NO bottom segment)
  GS510SZ:  0x7B (1111011) -- segments a,b,c,d,f,g (with bottom segment)
```

If you're adapting this for another VS-series board, check your "9" encoding
first -- it may differ from the GS510SZ reference table.
