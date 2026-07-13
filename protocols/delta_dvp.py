from pymodbus.client import ModbusTcpClient, ModbusSerialClient
from .modbus_common import read_modbus_tags


class DeltaDvpReader:
    """
    Delta DVP Series PLC - đọc qua Modbus TCP hoặc Modbus RTU.
    PLC Delta hỗ trợ Modbus chuẩn nên dùng được thẳng modbus_tcp/rtu,
    class này chỉ là wrapper với tham số mặc định đúng cho Delta.

    Tương thích:
        DVP-ES/EX/EC/EH/EH3 (cổng RS232/RS485 tích hợp)
        DVP-SV/SV2/SX2 (cổng RS232/RS485)
        DVP-ES3 (cổng Ethernet tích hợp — dùng modbus_tcp thẳng)
        DVP-EH3 (module DVP-ENET — dùng modbus_tcp)

    Địa chỉ thanh ghi Modbus (address = số thập phân):
        D register:   40001 + n  → address = n       (vd: D0 → address "0")
        M coil:       0 + n      → address = n (đọc coil) (vd: M0 → address "0")
        Y output:     0x500 + n  → address = "1280" + n

    Cấu hình RS485 trên PLC (phần mềm WPL Soft / DIADesigner):
        Baud: 9600 (mặc định), Parity: E (Even), Stopbits: 1, Slave: 1

    Cấu hình Ethernet (DVP-ES3):
        IP đặt trong phần mềm, Modbus TCP port 502

    Connection config (RS485):
        {
            "port": "/dev/ttyUSB0",
            "baudrate": 9600,
            "parity": "E",
            "stopbits": 1,
            "slave_id": 1
        }

    Connection config (TCP):
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
                timeout=3,
            )
        else:
            self.client = ModbusSerialClient(
                port=self.connection["port"],
                baudrate=self.connection.get("baudrate", 9600),
                parity=self.connection.get("parity", "E"),   # Delta mặc định Even
                stopbits=self.connection.get("stopbits", 1),
                bytesize=8,
                timeout=3,
            )
        if not self.client.connect():
            raise ConnectionError(
                f"Không kết nối được Delta DVP. "
                f"Kiểm tra parity=E (Even) và baudrate={self.connection.get('baudrate',9600)}"
            )

    def read_tags(self, tags):
        if not self.client or not self.client.connected:
            self.connect()
        return read_modbus_tags(self.client, self.slave_id, tags)

    def close(self):
        if self.client:
            self.client.close()
