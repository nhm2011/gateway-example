from pymodbus.client import ModbusSerialClient
import time

c = ModbusSerialClient(port='COM8', baudrate=9600, parity='E', stopbits=1, bytesize=8, timeout=2)
c.connect()

def call(fn, *args, **kwargs):
    for kw in ("slave", "unit", "device_id"):
        try:
            return fn(*args, **kwargs, **{kw: 1})
        except TypeError:
            continue
    return fn(*args, **kwargs)

# Nhập khoảng quét từ bàn phím
try:
    start_addr = int(input("Nhập địa chỉ coil bắt đầu: "))
    end_addr = int(input("Nhập địa chỉ coil kết thúc: "))
    
    print(f"\nBắt đầu quét từ {start_addr} đến {end_addr}...")
    print("Nhấn Ctrl+C để dừng.\n")

    # Sử dụng range(start, end + 1) để bao gồm cả số end_addr
    for addr in range(start_addr, end_addr + 1):
        print(f"--> Đang bật coil {addr} ...", end=" ", flush=True)
        call(c.write_coil, addr, True)
        time.sleep(1.5)
        call(c.write_coil, addr, False)
        print("xong")
        time.sleep(0.3)

except ValueError:
    print("Vui lòng nhập số nguyên hợp lệ.")
except KeyboardInterrupt:
    print("\nĐã dừng quét theo yêu cầu.")
finally:
    c.close()
    print("Đã đóng kết nối.")