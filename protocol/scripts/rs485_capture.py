import serial
import time
import sys

PORT = "COM9"
BAUD = 115200

print("RS485 Balboa Button Capture — 115200 8N1")
print("=" * 70)
print("Press Enter to mark a button press event.")
print("Type the button name then Enter (e.g., 'temp up', 'jets', 'lights')")
print("Type 'q' to quit and save the capture.\n")

ser = serial.Serial(
    port=PORT,
    baudrate=BAUD,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    timeout=0.1,
)
ser.reset_input_buffer()

log = []
start_time = time.time()
marker_count = 0

import threading
import queue

input_queue = queue.Queue()

def input_thread():
    while True:
        try:
            line = input()
            input_queue.put(line)
        except EOFError:
            break

t = threading.Thread(target=input_thread, daemon=True)
t.start()

print(f"[{0.0:8.3f}] Listening... (type button name + Enter to mark, 'q' to quit)\n")

last_print_time = 0
unique_patterns = {}

try:
    while True:
        # Check for user input
        try:
            user_input = input_queue.get_nowait()
            if user_input.strip().lower() == 'q':
                break
            elapsed = time.time() - start_time
            marker_count += 1
            marker = f"===== MARKER {marker_count}: [{user_input.strip()}] at {elapsed:.3f}s ====="
            log.append(marker)
            print(f"\n  >>> {marker}\n")
        except queue.Empty:
            pass

        # Read data
        data = ser.read(256)
        if data:
            elapsed = time.time() - start_time
            hex_str = " ".join(f"{b:02X}" for b in data)
            entry = f"[{elapsed:8.3f}] ({len(data):3d} bytes) {hex_str}"
            log.append(entry)

            # Print every chunk so user can see live data
            # But summarize repeating patterns
            pattern = data[:8] if len(data) >= 8 else data
            pattern_hex = " ".join(f"{b:02X}" for b in pattern)

            if elapsed - last_print_time > 0.5 or pattern_hex not in unique_patterns:
                print(f"[{elapsed:8.3f}] {hex_str[:80]}")
                if len(hex_str) > 80:
                    print(f"           {hex_str[80:160]}")
                last_print_time = elapsed

            if pattern_hex not in unique_patterns:
                unique_patterns[pattern_hex] = 0
            unique_patterns[pattern_hex] += 1

except KeyboardInterrupt:
    pass

ser.close()

# Save full log
outfile = "rs485_capture.txt"
with open(outfile, "w") as f:
    f.write(f"RS485 Capture — {PORT} @ {BAUD} baud\n")
    f.write(f"Duration: {time.time() - start_time:.1f}s\n")
    f.write(f"Markers: {marker_count}\n")
    f.write("=" * 70 + "\n\n")
    for line in log:
        f.write(line + "\n")
    f.write("\n" + "=" * 70 + "\n")
    f.write("UNIQUE PATTERNS SEEN (first 8 bytes):\n")
    for pat, count in sorted(unique_patterns.items(), key=lambda x: -x[1]):
        f.write(f"  {count:6d}x  {pat}\n")

print(f"\n{'=' * 70}")
print(f"Capture saved to {outfile}")
print(f"Duration: {time.time() - start_time:.1f}s | Markers: {marker_count}")
print(f"\nUnique patterns (first 8 bytes):")
for pat, count in sorted(unique_patterns.items(), key=lambda x: -x[1]):
    print(f"  {count:6d}x  {pat}")
