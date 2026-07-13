from pymodbus.client import ModbusSerialClient
from .modbus_common import read_modbus_tags


class ModbusRtuReader:
    """
    Modbus RTU qua cổng serial — dùng cho cả RS485 và RS232.

    RS485 (phổ biến nhất trong công nghiệp VN):
        - Cáp 2 dây (A+, B-), khoảng cách tới 1200m
        - Nối nhiều thiết bị trên cùng 1 đường bus (slave_id phân biệt)
        - Converter: USB-RS485 (chip CP2102/CH340/FTDI) → Linux: /dev/ttyUSB0, Windows: COM3...
        - Biến tần Mitsubishi, Delta, Schneider, LS/LG, đồng hồ điện CHINT, Selec...

    RS232 (thiết bị cũ, PLC đời đầu):
        - Cáp 3 dây (TXD, RXD, GND), DB9/DB25, tối đa 15m, chỉ 1 thiết bị/cổng
        - Converter: USB-RS232 (chip FTDI FT232/Prolific PL2303) → Linux: /dev/ttyUSB0, Windows: COMx
        - PLC LS/LG XGB/XGI, Mitsubishi FX (cổng RS232), Omron CP1/CJ (cổng RS232)
        - Lưu ý: RS232 và RS485 dùng CÙNG CODE pymodbus, chỉ khác tham số vật lý

    PLC LS (LG) qua USB:
        - Baud: 9600 (mặc định), có thể 19200 hoặc 38400 tuỳ cấu hình PLC
        - Parity: E (Even) — quan trọng, sai parity sẽ luôn lỗi
        - Stopbits: 1
        - Slave ID: 1 (mặc định, đặt trong phần mềm XG5000)
        - Windows: COM8 (hoặc số khác, xem Device Manager)
        - Linux/Raspberry Pi: /dev/ttyUSB0

    PLC Mitsubishi FX qua RS232:
        - Baud: 9600, Parity: E (Even), Stopbits: 1
        - Lưu ý: FX cần enable Modbus trong phần mềm GX Works

    Biến tần Delta VFD-E/M:
        - Baud: 9600, Parity: N (None), Stopbits: 2, Slave: 1
    """

    def __init__(self, connection):
        self.port = connection["port"]               # Windows: "COM8", Linux: "/dev/ttyUSB0"
        self.baudrate = connection.get("baudrate", 9600)
        self.parity = connection.get("parity", "N")  # N=None, E=Even, O=Odd — LS/Mitsubishi thường dùng E
        self.stopbits = connection.get("stopbits", 1)
        self.bytesize = connection.get("bytesize", 8)
        self.slave_id = connection.get("slave_id", 1)
        self.timeout = connection.get("timeout", 3)
        self.client = None

    def connect(self):
        self.client = ModbusSerialClient(
            port=self.port,
            baudrate=self.baudrate,
            parity=self.parity,
            stopbits=self.stopbits,
            bytesize=self.bytesize,
            timeout=self.timeout,
        )
        connected = self.client.connect()
        if not connected:
            raise ConnectionError(
                f"Không mở được cổng {self.port}. "
                f"Kiểm tra: cổng đúng chưa (Device Manager/ls /dev/tty*), "
                f"không có phần mềm khác đang chiếm cổng không (XG5000, GX Works...)."
            )
        return connected

    def read_tags(self, tags):
        if not self.client or not self.client.connected:
            self.connect()
        return read_modbus_tags(self.client, self.slave_id, tags)

    def close(self):
        if self.client:
            self.client.close()


# Alias - RS232 và RS485 dùng cùng class, phân biệt bằng tài liệu và tham số parity/stopbits
class ModbusRs232Reader(ModbusRtuReader):
    """RS232 — cùng code với RS485, chỉ khác cáp/converter vật lý."""
    pass
