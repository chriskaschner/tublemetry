import serial
import sys
import time

BAUD_RATES = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200, 230400, 250000, 460800, 921600]
PORT = "COM9"
LISTEN_SECONDS = 3

print(f"Scanning {PORT} across {len(BAUD_RATES)} baud rates ({LISTEN_SECONDS}s each)\n")
print("=" * 70)

for baud in BAUD_RATES:
    try:
        ser = serial.Serial(
            port=PORT,
            baudrate=baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.5,
        )
        print(f"\n>> {baud} baud")

        # Flush any stale data
        ser.reset_input_buffer()

        start = time.time()
        total_bytes = 0
        chunks = []

        while time.time() - start < LISTEN_SECONDS:
            data = ser.read(256)
            if data:
                total_bytes += len(data)
                chunks.append(data)

        ser.close()

        if total_bytes == 0:
            print("   (no data received)")
        else:
            print(f"   {total_bytes} bytes received")
            combined = b"".join(chunks)
            # Show first 128 bytes in hex + ASCII
            preview = combined[:128]
            for offset in range(0, len(preview), 16):
                row = preview[offset:offset + 16]
                hex_part = " ".join(f"{b:02X}" for b in row)
                ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
                print(f"   {offset:04X}  {hex_part:<48s}  {ascii_part}")
            if len(combined) > 128:
                print(f"   ... ({total_bytes - 128} more bytes)")
    except serial.SerialException as e:
        print(f"\n>> {baud} baud — ERROR: {e}")
    except KeyboardInterrupt:
        print("\nStopped by user.")
        sys.exit(0)

print("\n" + "=" * 70)
print("Scan complete.")
