from pymodbus.client import ModbusSerialClient
import time

c = ModbusSerialClient(port='COM3', baudrate=9600, parity='E', stopbits=1, bytesize=8, timeout=2)
c.connect()

def call(fn, *args, **kwargs):
    for kw in ("slave", "unit", "device_id"):
        try:
            return fn(*args, **kwargs, **{kw: 1})
        except TypeError:
            continue
    return fn(*args, **kwargs)

print("Sẽ lần lượt bật từng coil từ 0 đến 49, mỗi cái cách nhau 2 giây.")
print("BẠN NHÌN ĐÈN M4 TRÊN PLC - khi nào thấy nó sáng thì ghi lại số đang hiện.")
print("Nhấn Ctrl+C để dừng giữa chừng khi đã thấy đèn sáng.\n")

for addr in range(50):
    print(f"--> Đang bật coil {addr} ...", end=" ", flush=True)
    call(c.write_coil, addr, True)
    time.sleep(1.5)
    call(c.write_coil, addr, False)  # tắt lại trước khi qua coil tiếp theo
    print("xong")
    time.sleep(0.3)

c.close()
print("\nQuét xong toàn bộ 0-49.")
