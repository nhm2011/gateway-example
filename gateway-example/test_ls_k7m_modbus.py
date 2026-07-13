"""
Script test Modbus RTU cho LS K7M-DR40S
Chương trình PLC đang test: M0-M5 -> P40-P45

Cách dùng:
1. Sửa SERIAL_PORT cho đúng cổng COM của anh (vd: 'COM3' trên Windows, '/dev/ttyUSB0' trên Linux)
2. Chạy: python test_ls_k7m_modbus.py
3. Xem PLC (đèn P40-P45) có sáng theo lệnh ghi coil không

Yêu cầu: pip install pymodbus==3.13.1 --break-system-packages (theo ghi chú trước đó anh dùng bản này)
"""

from pymodbus.client import ModbusSerialClient
import time

SERIAL_PORT = "COM3"   # <-- SỬA CHO ĐÚNG CỔNG COM CỦA ANH (kiểm tra lại trong Device Manager)
BAUDRATE = 9600
SLAVE_ID = 1            # Station Number đã đặt = 1 trong KGLWIN

import logging
logging.basicConfig()
logging.getLogger("pymodbus").setLevel(logging.DEBUG)  # bật log chi tiết từng byte gửi/nhận

client = ModbusSerialClient(
    port=SERIAL_PORT,
    baudrate=BAUDRATE,
    parity="E",         # Đã đổi khớp với Parity Bit = Even trong KGLWIN
    stopbits=1,
    bytesize=8,
    timeout=2,          # tăng timeout để loại trừ do PLC phản hồi chậm
    retries=1,          # giảm retry để debug nhanh, thấy lỗi ngay
)

def try_read_coils(address, count, label):
    try:
        result = client.read_coils(address=address, count=count, device_id=SLAVE_ID)
        if result.isError():
            print(f"[{label}] LỖI: {result}")
        else:
            print(f"[{label}] OK -> {result.bits[:count]}")
    except Exception as e:
        print(f"[{label}] EXCEPTION: {e}")

def try_write_coil(address, value, label):
    try:
        result = client.write_coil(address=address, value=value, device_id=SLAVE_ID)
        if result.isError():
            print(f"[{label}] GHI LỖI: {result}")
        else:
            print(f"[{label}] GHI OK -> address={address}, value={value}")
    except Exception as e:
        print(f"[{label}] GHI EXCEPTION: {e}")

def try_read_holding(address, count, label):
    try:
        result = client.read_holding_registers(address=address, count=count, device_id=SLAVE_ID)
        if result.isError():
            print(f"[{label}] LỖI: {result}")
        else:
            print(f"[{label}] OK -> {result.registers}")
    except Exception as e:
        print(f"[{label}] EXCEPTION: {e}")


if __name__ == "__main__":
    if not client.connect():
        print(f"KHÔNG kết nối được cổng {SERIAL_PORT}. Kiểm tra lại cáp / cổng COM / driver USB-RS232.")
        exit(1)

    print("Đã kết nối cổng serial. Bắt đầu dò thử...\n")

    # --- Bước 1: Thử đọc coil tại address 0 (nghi ngờ ứng với M0 hoặc P40) ---
    print("=== Thử đọc coil offset 0-10 (map thử cho M hoặc P) ===")
    try_read_coils(0, 10, "coil@0")

    # --- Bước 2: Thử ghi thử coil address 0 = True, xem đèn P40 có sáng không ---
    print("\n=== Thử ghi coil address 0 = ON, quan sát đèn P40 trên PLC ===")
    try_write_coil(0, True, "write@0")
    time.sleep(1)
    try_read_coils(0, 10, "coil@0 sau khi ghi")

    print("\nNếu đèn P40 sáng -> address 0 = M0 (offset tuyến tính, dùng luôn công thức address = M_number)")
    print("Nếu không sáng -> thử các offset khác bên dưới (bỏ comment để test thêm)")

    # --- Bước 3 (dự phòng): thử các offset phổ biến khác nếu bước 2 không khớp ---
    # try_write_coil(40, True, "write@40 (thử offset = P-area bit number)")
    # try_read_holding(0, 10, "holding@0 (nếu M-area map vào holding register thay vì coil)")

    # Tắt lại trước khi thoát để an toàn
    try_write_coil(0, False, "reset write@0 OFF")

    client.close()
    print("\nĐã đóng kết nối.")
