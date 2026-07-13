from pymodbus.client import ModbusTcpClient, ModbusSerialClient
from .modbus_common import read_modbus_tags


class LsXgbReader:
    """
    PLC LS Industrial Systems (trước là LG) - dòng XGB, XGI, XGK, XGR.
    Hỗ trợ Modbus RTU (RS232/RS485) và Modbus TCP (qua module Ethernet).

    Tương thích:
        XGB (XBC-DN64H, XBC-DN32H...) — cổng RS232 + RS485 tích hợp
        XGI (XGI-CPUE, XGI-CPUU...) — cổng RS232, cần module XGL-EFMT cho Ethernet
        XGK — cổng RS232
        XGR — redundant PLC

    Lưu ý quan trọng:
        LS PLC KHÔNG có Modbus sẵn theo mặc định.
        Phải vào XG5000 → Project → PLC Setting → Communication → Cấu hình Modbus RTU:
            - Enable Modbus Slave
            - Baud Rate: 9600 (hoặc 19200, 38400)
            - Parity: EVEN ← rất quan trọng, nếu để None sẽ luôn lỗi
            - Stop Bit: 1
            - Slave Address: 1

    Kết nối qua USB (phổ biến nhất khi test):
        - Cắm cáp USB-RS232 (cáp đi kèm PLC hoặc mua riêng)
        - Windows: xuất hiện COMx trong Device Manager → Ports
        - Mở XG5000 → Online → Connect → chọn COMx → OK
        - SAU KHI lập trình xong, THOÁT XG5000 (nhả cổng COM)
        - Rồi mới chạy gateway — hai phần mềm KHÔNG thể dùng cùng 1 cổng COM

    Kết nối qua RS485 (triển khai thực tế):
        - Cổng COM2 của XGB (RJ45 hoặc terminal): dùng RS485
        - Cần converter USB-RS485
        - Nhiều XGB trên cùng bus RS485, phân biệt bằng slave_id

    Vùng nhớ Modbus của XGB:
        %MW0    → Holding Register, address = 0      (Data word, đọc/ghi)
        %IW0    → Input Register, address = 0         (Input word, chỉ đọc)
        %MX0    → Coil, address = 0                   (Bit, đọc/ghi) — dùng data_type="coil"
        %IX0    → Discrete Input, address = 0         (Bit input, chỉ đọc)

    ĐIỀU KHIỂN OUTPUT (M, Y) — RẤT QUAN TRỌNG:
        Để bật/tắt M1, M2, M3... (coil bit), PHẢI khai báo:
            { "tag_key": "m1", "address": "1", "data_type": "coil" }
        KHÔNG dùng data_type="int16" cho coil — sẽ gửi sai function code (FC06 thay vì FC05),
        PLC nhận lệnh nhưng ngõ ra không đổi trạng thái (đây là lỗi rất hay gặp).

    ĐIỀU KHIỂN BIT TRONG D REGISTER (D0.0, D0.1...):
        D là vùng nhớ word 16-bit, muốn bật/tắt 1 bit cụ thể trong D dùng:
            { "tag_key": "d0_bit3", "address": "0", "data_type": "bit:3" }
        Gateway sẽ tự đọc word D0, set/clear bit thứ 3, rồi ghi lại cả word — an toàn,
        không ảnh hưởng các bit khác trong cùng D register.

    Connection config (RS232 qua USB):
        {
            "port": "COM8",         ← Windows — xem Device Manager
            "baudrate": 9600,
            "parity": "E",          ← PHẢI là Even, đây là nguồn lỗi phổ biến nhất
            "stopbits": 1,
            "slave_id": 1,
            "timeout": 5            ← tăng timeout nếu hay bị timeout
        }

    Connection config (Ethernet qua module XGL-EFMT):
        {
            "ip": "192.168.1.10",
            "port": 502,
            "slave_id": 1
        }
    """

    def __init__(self, connection):
        self.connection = connection
        self.mode = "tcp" if "ip" in connection else "rtu"
        self.slave_id = connection.get("slave_id", 1)
        self.client = None

    def connect(self):
        if self.mode == "tcp":
            self.client = ModbusTcpClient(
                self.connection["ip"],
                port=self.connection.get("port", 502),
                timeout=self.connection.get("timeout", 3),
            )
        else:
            port = self.connection["port"]
            parity = self.connection.get("parity", "E")
            baudrate = self.connection.get("baudrate", 9600)

            if parity != "E":
                print(f"[ls_xgb] CẢNH BÁO: parity='{parity}' — LS XGB mặc định dùng Even (E). "
                      "Nếu đọc không được, thử đổi sang parity='E'")

            self.client = ModbusSerialClient(
                port=port,
                baudrate=baudrate,
                parity=parity,
                stopbits=self.connection.get("stopbits", 1),
                bytesize=8,
                timeout=self.connection.get("timeout", 5),
            )

        if not self.client.connect():
            port_info = self.connection.get("port") or self.connection.get("ip")
            raise ConnectionError(
                f"Không kết nối được LS XGB tại '{port_info}'.\n"
                f"Kiểm tra:\n"
                f"  1. Đã bật Modbus trong XG5000 chưa? (PLC Setting → Communication → Enable Modbus)\n"
                f"  2. Parity phải là E (Even)\n"
                f"  3. XG5000 có đang mở và chiếm cổng COM không? → Đóng XG5000 rồi thử lại\n"
                f"  4. Cổng COM đúng chưa? Kiểm tra Device Manager"
            )

    def read_tags(self, tags):
        if not self.client or not self.client.connected:
            self.connect()
        return read_modbus_tags(self.client, self.slave_id, tags)

    def close(self):
        if self.client:
            self.client.close()
