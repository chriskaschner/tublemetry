import serial
import time
import sys
import threading
import queue

PORT = "COM9"
BAUD = 115200
DURATION = 30

print("RS485 Jets Capture — 115200 8N1")
print("=" * 70)
print(f"Capturing for {DURATION}s. Press jets a few times with pauses between.")
print("Press Enter each time you press jets (type 'q' to stop early).\n")

ser = serial.Serial(port=PORT, baudrate=BAUD, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=0.1)
ser.reset_input_buffer()

log = []
start_time = time.time()
marker_count = 0

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

print(f"[{0.0:8.3f}] Listening...\n")

try:
    while time.time() - start_time < DURATION:
        try:
            user_input = input_queue.get_nowait()
            if user_input.strip().lower() == 'q':
                break
            elapsed = time.time() - start_time
            marker_count += 1
            marker = f"===== MARKER {marker_count}: [jets] at {elapsed:.3f}s ====="
            log.append(marker)
            print(f"\n  >>> {marker}\n")
        except queue.Empty:
            pass

        data = ser.read(256)
        if data:
            elapsed = time.time() - start_time
            hex_str = " ".join(f"{b:02X}" for b in data)
            entry = f"[{elapsed:8.3f}] ({len(data):3d} bytes) {hex_str}"
            log.append(entry)
            # Only print lines that differ from idle pattern
            if not all(b in (0xFE, 0x06, 0x70, 0xE6, 0x00) for b in data):
                print(f"[{elapsed:8.3f}] ** {hex_str[:120]}")
except KeyboardInterrupt:
    pass

ser.close()

outfile = "rs485_jets.txt"
with open(outfile, "w") as f:
    for line in log:
        f.write(line + "\n")

print(f"\n{'=' * 70}")
print(f"Saved to {outfile} | Duration: {time.time() - start_time:.1f}s | Markers: {marker_count}")
