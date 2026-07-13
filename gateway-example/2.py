import serial
import time

ser = serial.Serial(
    "COM3",
    baudrate=9600,
    bytesize=8,
    parity='E',
    stopbits=1,
    timeout=1
)

# FC03 đọc Holding Register 0
req = bytes([
    0x01, 0x03,
    0x00, 0x00,
    0x00, 0x01,
    0x84, 0x0A      # CRC của 01 03 00 00 00 01
])

ser.write(req)

time.sleep(0.5)

data = ser.read(100)

print(data)
print(data.hex(" "))