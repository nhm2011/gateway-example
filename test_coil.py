from pymodbus.client import ModbusSerialClient
import time

c = ModbusSerialClient(port='COM3', baudrate=9600, parity='E', stopbits=1, bytesize=8, timeout=3)
c.connect()

def call(fn, *args, **kwargs):
    for kw in ("slave", "unit", "device_id"):
        try:
            return fn(*args, **kwargs, **{kw: 1})
        except TypeError:
            continue
    return fn(*args, **kwargs)

print('Ghi coil 4 = ON...')
r = call(c.write_coil, 4, True)
print('Ket qua ghi:', r)

time.sleep(0.5)

r2 = call(c.read_coils, 4, count=1)
print('Doc lai coil 4:', r2.bits[0] if not r2.isError() else 'loi')

c.close()
