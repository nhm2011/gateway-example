"""
Script quét tuần tự địa chỉ coil Modbus cho LS K7M-DR40S
Giữ từng địa chỉ ON trong 2 giây để anh quan sát đèn P40-P45 trên PLC.

QUAN TRỌNG: Trước khi chạy, kiểm tra công tắc RUN/STOP trên PLC phải ở vị trí RUN,
nếu không chương trình ladder không chạy và đèn sẽ không bao giờ sáng dù ghi coil OK.

Cách dùng:
1. Sửa SERIAL_PORT, BAUDRATE, PARITY cho đúng
2. Chạy: python scan_ls_k7m_coils.py
3. Quan sát đèn P40-P45 trong lúc script chạy, ghi lại address nào làm đèn sáng
"""

from pymodbus.client import ModbusSerialClient
import time

SERIAL_PORT = "COM8"
BAUDRATE = 9600
PARITY = "E"
SLAVE_ID = 1

# Công thức chính thức theo tài liệu LS Master-K80S (Modbus addressing table):
#   P area (I/O relay)      -> offset 0
#   M area (auxiliary relay) -> offset 4096 (h1000)
M_BASE = 4096
P_BASE = 0

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

    print("Đã kết nối. Test ghi M0-M5 (address 4096-4101), đọc lại P40-P45 (address 40-45)\n")
    print("QUAN SÁT đèn P40-P45 trên PLC trong lúc chạy!\n")

    for i in range(6):  # M0..M5 -> P40..P45
        m_addr = M_BASE + i
        # P4y: word=4, bit=y (hex) -> linear = 4*16 + y
        p_addr = 4 * 16 + i

        # Ghi M_i = True
        result = client.write_coil(address=m_addr, value=True, device_id=SLAVE_ID)
        if result.isError():
            print(f"M{i} (addr={m_addr}): GHI LỖI -> {result}")
            continue
        print(f"M{i} (addr={m_addr}): đã BẬT -> quan sát đèn P4{i} NGAY BÂY GIỜ")
        time.sleep(2)

        # Đọc lại P tương ứng để xác nhận qua phần mềm (không chỉ mắt thường)
        read_result = client.read_coils(address=p_addr, count=1, device_id=SLAVE_ID)
        if not read_result.isError():
            print(f"  -> Đọc lại P4{i} (addr={p_addr}) qua Modbus: {read_result.bits[0]}")

        # Tắt lại
        client.write_coil(address=m_addr, value=False, device_id=SLAVE_ID)
        time.sleep(0.3)

    print("\nĐã test xong M0-M5. Đóng kết nối.")
    client.close()


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
