from pymodbus.client import ModbusSerialClient
import time
import logging

logging.basicConfig()
logging.getLogger("pymodbus").setLevel(logging.DEBUG)

SERIAL_PORT = "COM3"   # sửa đúng cổng đang dùng
BAUDRATE = 9600
PARITY = "E"
SLAVE_ID = 1

client = ModbusSerialClient(
    port=SERIAL_PORT, baudrate=BAUDRATE, parity=PARITY,
    stopbits=1, bytesize=8, timeout=1,
)

if not client.connect():
    print("KHONG ket noi duoc cong", SERIAL_PORT)
    exit(1)

print("Da ket noi. Ghi D0 = 1234, doc lai...\n")

w = client.write_register(address=0, value=1234, device_id=SLAVE_ID)
print("Ghi D0=1234:", "OK" if not w.isError() else f"LOI: {w}")

time.sleep(0.3)

r = client.read_holding_registers(address=0, count=1, device_id=SLAVE_ID)
print("RAW RESPONSE OBJECT:", r)
print("isError():", r.isError())
if hasattr(r, "registers"):
    print("registers:", r.registers)

client.close()
