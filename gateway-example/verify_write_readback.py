"""
Script kiểm tra dứt điểm: GHI rồi ĐỌC LẠI NGAY tại nhiều địa chỉ,
để xác định giá trị ghi có thực sự được PLC lưu lại hay không
(bất kể đèn LED có sáng hay không).

Chạy: python verify_write_readback.py
"""

from pymodbus.client import ModbusSerialClient
import time

SERIAL_PORT = "COM3"   # đổi đúng cổng đang dùng
BAUDRATE = 9600
PARITY = "E"
SLAVE_ID = 1

# Danh sách địa chỉ cần kiểm tra
TEST_ADDRESSES = [0, 40, 64, 4096, 4160, 8192]

client = ModbusSerialClient(
    port=SERIAL_PORT,
    baudrate=BAUDRATE,
    parity=PARITY,
    stopbits=1,
    bytesize=8,
    timeout=1,
)


def main():
    if not client.connect():
        print(f"KHÔNG kết nối được cổng {SERIAL_PORT}.")
        return

    print("Kiểm tra GHI rồi ĐỌC LẠI NGAY tại từng địa chỉ:\n")

    for addr in TEST_ADDRESSES:
        before = client.read_coils(address=addr, count=1, device_id=SLAVE_ID)
        before_val = before.bits[0] if not before.isError() else "LỖI ĐỌC"

        write_result = client.write_coil(address=addr, value=True, device_id=SLAVE_ID)
        write_ok = not write_result.isError()

        time.sleep(0.3)

        after = client.read_coils(address=addr, count=1, device_id=SLAVE_ID)
        after_val = after.bits[0] if not after.isError() else "LỖI ĐỌC"

        match = "GIU DUNG GIA TRI" if after_val is True else "KHONG GIU (hoac loi)"

        print(f"address={addr:6d} | truoc={before_val} | ghi_OK={write_ok} | sau_ghi={after_val}  {match}")

        client.write_coil(address=addr, value=False, device_id=SLAVE_ID)
        time.sleep(0.2)

    print("\nHoan tat. Dong ket noi.")
    client.close()


if __name__ == "__main__":
    main()
