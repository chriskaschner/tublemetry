import os, csv

filepath = os.path.join(os.environ["USERPROFILE"], "OneDrive - Electronic Theatre Controls, Inc", "Desktop", "485", "OH.csv")

SR = 1_000_000

# Read only CH4 (Pin 5, display content) and CH5 (Pin 6, display refresh)
ch4, ch5 = [], []
with open(filepath, 'r') as f:
    reader = csv.reader(f)
    next(reader)
    for row in reader:
        ch4.append(int(row[4]))
        ch5.append(int(row[5]))

print(f"Samples: {len(ch4)} ({len(ch4)/SR:.1f}s)")

# The display is flashing "OH" — 500ms on, 500ms off
# Let's look at CH5 (the display refresh stream with more transitions)
# and try to find the on/off pattern

# Find all transition timestamps on CH4
transitions_4 = []
for i in range(1, len(ch4)):
    if ch4[i] != ch4[i-1]:
        transitions_4.append((i, ch4[i]))

transitions_5 = []
for i in range(1, len(ch5)):
    if ch5[i] != ch5[i-1]:
        transitions_5.append((i, ch5[i]))

print(f"CH4 transitions: {len(transitions_4)}")
print(f"CH5 transitions: {len(transitions_5)}")

# Find data burst boundaries on CH5
# Look for gaps > 1ms between transitions (idle periods between bursts)
bursts_5 = []
if transitions_5:
    current_burst_start = transitions_5[0][0]
    current_burst_end = transitions_5[0][0]
    for i in range(1, len(transitions_5)):
        gap = transitions_5[i][0] - transitions_5[i-1][0]
        if gap > 1000:  # >1ms gap = new burst
            bursts_5.append((current_burst_start, current_burst_end))
            current_burst_start = transitions_5[i][0]
        current_burst_end = transitions_5[i][0]
    bursts_5.append((current_burst_start, current_burst_end))

print(f"\nCH5 data bursts (gaps > 1ms): {len(bursts_5)}")
for i, (start, end) in enumerate(bursts_5[:20]):
    duration_us = (end - start)
    print(f"  Burst {i+1}: {start/SR*1000:.1f}ms - {end/SR*1000:.1f}ms (duration: {duration_us}µs)")

# Same for CH4
bursts_4 = []
if transitions_4:
    current_burst_start = transitions_4[0][0]
    current_burst_end = transitions_4[0][0]
    for i in range(1, len(transitions_4)):
        gap = transitions_4[i][0] - transitions_4[i-1][0]
        if gap > 1000:
            bursts_4.append((current_burst_start, current_burst_end))
            current_burst_start = transitions_4[i][0]
        current_burst_end = transitions_4[i][0]
    bursts_4.append((current_burst_start, current_burst_end))

print(f"\nCH4 data bursts (gaps > 1ms): {len(bursts_4)}")
for i, (start, end) in enumerate(bursts_4[:20]):
    duration_us = (end - start)
    print(f"  Burst {i+1}: {start/SR*1000:.1f}ms - {end/SR*1000:.1f}ms (duration: {duration_us}µs)")

# Look at the timing between bursts to find the 500ms on/off pattern
if len(bursts_5) > 5:
    print(f"\nCH5 gaps between bursts (ms):")
    for i in range(1, min(len(bursts_5), 20)):
        gap = (bursts_5[i][0] - bursts_5[i-1][1]) / SR * 1000
        print(f"  Burst {i} -> {i+1}: {gap:.1f}ms")
