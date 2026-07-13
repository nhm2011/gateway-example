import serial
import time

ser = serial.Serial(
    port="COM8",      # hoặc COM3
    baudrate=9600,
    bytesize=8,
    parity='E',
    stopbits=1,
    timeout=1
)

print("Opened:", ser.port)

# ===== THAY frame này sau =====
tx = b'\x05'
# ==============================

print("TX:", tx.hex(" "))

ser.write(tx)

time.sleep(0.5)

rx = ser.read(100)

print("Length:", len(rx))
print("RX HEX:", rx.hex(" "))
print("RX RAW:", rx)

ser.close()