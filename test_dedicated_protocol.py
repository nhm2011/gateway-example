"""
Dedicated Protocol (Cnet gốc của LS Master-K / K7M) - đọc/ghi trực tiếp
bằng TÊN THIẾT BỊ (%MX000, %PX040...) thay vì đoán địa chỉ Modbus.

QUAN TRỌNG - đổi cấu hình trong KGLWIN trước khi chạy:
  Tab Comm. -> mục "Dedicated" (không phải Modbus) -> chọn "Slave"
  (bỏ chọn Modbus Slave đang dùng trước đó)
  Giữ nguyên Baud/Parity/Data/Stop bit như hiện tại (9600, Even, 8, 1)
  Station Number giữ = 1 (hoặc số đang đặt)
  Download Parameter xuống PLC + khởi động lại

Cách dùng:
    python test_dedicated_protocol.py
"""

import serial
import time

SERIAL_PORT = "COM8"
BAUDRATE = 9600
PARITY = serial.PARITY_EVEN   # đổi nếu KGLWIN đang để khác
STATION_NO = 1

ENQ = 0x05
ACK = 0x06
NAK = 0x15
EOT = 0x04
ETX = 0x03


def bcc(frame_bytes: bytes) -> bytes:
    """BCC = byte thấp của tổng tất cả byte trong frame, chuyển thành 2 ký tự ASCII hex."""
    total = sum(frame_bytes) & 0xFF
    return f"{total:02X}".encode("ascii")


def build_read_frame(station: int, device_name: str) -> bytes:
    """Xây khung lệnh đọc từng thiết bị (RSS - individual reading)."""
    station_hex = f"{station:02X}".encode("ascii")
    command = b"r"          # chữ thường theo đúng ví dụ tài liệu
    cmd_type = b"SS"
    num_blocks = b"01"
    dev_name_b = device_name.encode("ascii")
    dev_len = f"{len(dev_name_b):02X}".encode("ascii")

    body = bytes([ENQ]) + station_hex + command + cmd_type + num_blocks + dev_len + dev_name_b + bytes([EOT])
    check = bcc(body)
    return body + check


def build_write_frame(station: int, device_name: str, bit_value: bool) -> bytes:
    """Xây khung lệnh ghi từng thiết bị (WSS - individual writing), cho thiết bị kiểu Bit."""
    station_hex = f"{station:02X}".encode("ascii")
    command = b"w"
    cmd_type = b"SS"
    num_blocks = b"01"
    dev_name_b = device_name.encode("ascii")
    dev_len = f"{len(dev_name_b):02X}".encode("ascii")
    data = b"01" if bit_value else b"00"

    body = bytes([ENQ]) + station_hex + command + cmd_type + num_blocks + dev_len + dev_name_b + data + bytes([EOT])
    check = bcc(body)
    return body + check


def send_and_receive(ser: serial.Serial, frame: bytes, label: str):
    ser.reset_input_buffer()
    ser.write(frame)
    print(f"[{label}] Gửi: {frame}")

    time.sleep(0.3)
    resp = ser.read(256)
    print(f"[{label}] Nhận: {resp}")

    if not resp:
        print(f"[{label}] KHÔNG CÓ PHẢN HỒI (timeout)")
        return None

    if resp[0] == ACK:
        print(f"[{label}] -> ACK (thành công)")
    elif resp[0] == NAK:
        print(f"[{label}] -> NAK (lỗi) - xem mã lỗi trong response")
    else:
        print(f"[{label}] -> Byte đầu lạ: {hex(resp[0])}")

    return resp


def main():
    ser = serial.Serial(
        port=SERIAL_PORT,
        baudrate=BAUDRATE,
        parity=PARITY,
        bytesize=serial.SEVENBITS,   # ASCII mode của Dedicated Protocol yêu cầu 7-bit, không phải 8-bit
        stopbits=serial.STOPBITS_ONE,
        timeout=1,
    )

    print(f"Đã mở cổng {SERIAL_PORT}\n")

    # --- Bước 1: Đọc trạng thái M0 hiện tại ---
    frame = build_read_frame(STATION_NO, "%MX000")
    send_and_receive(ser, frame, "READ M0")

    print()

    # --- Bước 2: Ghi M0 = 1 (ON) ---
    frame = build_write_frame(STATION_NO, "%MX000", True)
    send_and_receive(ser, frame, "WRITE M0=1")

    print("\n>>> QUAN SÁT ĐÈN P40 TRÊN PLC NGAY BÂY GIỜ <<<\n")
    time.sleep(2)

    # --- Bước 3: Đọc lại M0 để xác nhận đã lưu ---
    frame = build_read_frame(STATION_NO, "%MX000")
    send_and_receive(ser, frame, "READ M0 sau ghi")

    print()

    # --- Bước 4: Đọc P40 để xác nhận ladder đã copy sang ---
    frame = build_read_frame(STATION_NO, "%PX040")
    send_and_receive(ser, frame, "READ P40")

    time.sleep(1)

    # --- Bước 5: Tắt lại M0 ---
    frame = build_write_frame(STATION_NO, "%MX000", False)
    send_and_receive(ser, frame, "WRITE M0=0 (reset)")

    ser.close()
    print("\nĐã đóng kết nối.")


if __name__ == "__main__":
    main()
