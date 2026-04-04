import os, csv

filepath = os.path.join(os.environ["USERPROFILE"], "OneDrive - Electronic Theatre Controls, Inc", "Desktop", "485", "254.csv")

# Read only the active channels (4, 5, 6)
ch4, ch5, ch6 = [], [], []
with open(filepath, 'r') as f:
    reader = csv.reader(f)
    next(reader)  # skip header
    for row in reader:
        ch4.append(int(row[4]))
        ch5.append(int(row[5]))
        ch6.append(int(row[6]))

SAMPLE_RATE = 4_000_000
BAUD = 115200
SPB = SAMPLE_RATE / BAUD  # samples per bit ~34.72

def find_transitions(data, ch_name):
    """Find all transition points"""
    transitions = []
    for i in range(1, len(data)):
        if data[i] != data[i-1]:
            transitions.append((i, data[i]))
    print(f"{ch_name}: {len(transitions)} transitions")
    if transitions:
        # Show first few transition positions
        for t in transitions[:10]:
            print(f"  Sample {t[0]} -> {t[1]} (t={t[0]/SAMPLE_RATE*1000:.3f}ms)")
        if len(transitions) > 10:
            print(f"  ... and {len(transitions)-10} more")
    return transitions

def decode_uart_idle_high(data, ch_name):
    """Decode standard UART (idle=1, start bit=0)"""
    bytes_out = []
    i = 0
    n = len(data)
    while i < n - int(SPB * 10):
        if data[i] == 1 and data[i+1] == 0:  # falling edge = start bit
            start = i + 1
            # verify middle of start bit is 0
            mid = start + int(SPB * 0.5)
            if mid < n and data[mid] == 0:
                byte_val = 0
                valid = True
                for bit in range(8):
                    pos = start + int(SPB * (1.5 + bit))
                    if pos >= n:
                        valid = False
                        break
                    byte_val |= (data[pos] << bit)
                stop_pos = start + int(SPB * 9.5)
                if valid and stop_pos < n and data[stop_pos] == 1:
                    bytes_out.append((start, byte_val))
                    i = start + int(SPB * 10)
                    continue
        i += 1
    return bytes_out

def decode_uart_idle_low(data, ch_name):
    """Decode inverted UART (idle=0, start bit=1) - invert then decode"""
    inv = [1 - x for x in data]
    return decode_uart_idle_high(inv, ch_name)

print("=== Transition Analysis ===")
find_transitions(ch4, "CH4")
print()
find_transitions(ch5, "CH5")
print()
find_transitions(ch6, "CH6")

print("\n=== UART Decode ===")

# CH4 idles low
r = decode_uart_idle_low(ch4, "CH4")
if r:
    hexs = ' '.join(f'{b[1]:02X}' for b in r[:60])
    print(f"CH4 (idle-low/inverted): {len(r)} bytes")
    print(f"  {hexs}")

# CH5 idles low
r = decode_uart_idle_low(ch5, "CH5")
if r:
    hexs = ' '.join(f'{b[1]:02X}' for b in r[:60])
    print(f"CH5 (idle-low/inverted): {len(r)} bytes")
    print(f"  {hexs}")

# CH6 idles high
r = decode_uart_idle_high(ch6, "CH6")
if r:
    hexs = ' '.join(f'{b[1]:02X}' for b in r[:60])
    print(f"CH6 (idle-high/normal): {len(r)} bytes")
    print(f"  {hexs}")

# Also try CH4/CH5 normal and CH6 inverted just in case
r = decode_uart_idle_high(ch4, "CH4")
if r:
    hexs = ' '.join(f'{b[1]:02X}' for b in r[:60])
    print(f"CH4 (idle-high/normal): {len(r)} bytes")
    print(f"  {hexs}")

r = decode_uart_idle_high(ch5, "CH5")
if r:
    hexs = ' '.join(f'{b[1]:02X}' for b in r[:60])
    print(f"CH5 (idle-high/normal): {len(r)} bytes")
    print(f"  {hexs}")

r = decode_uart_idle_low(ch6, "CH6")
if r:
    hexs = ' '.join(f'{b[1]:02X}' for b in r[:60])
    print(f"CH6 (idle-low/inverted): {len(r)} bytes")
    print(f"  {hexs}")
