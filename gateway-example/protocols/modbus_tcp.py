from pymodbus.client import ModbusTcpClient
from .modbus_common import read_modbus_tags


class ModbusTcpReader:
    """Dùng cho PLC/thiết bị kết nối qua mạng LAN, vd: hầu hết PLC đời mới
    (Mitsubishi FX5U qua module Ethernet, Siemens S7-1200 qua Modbus TCP gateway,
    Delta, LS/LG, Omron NX...)."""

    def __init__(self, connection):
        self.ip = connection["ip"]
        self.port = connection.get("port", 502)
        self.slave_id = connection.get("slave_id", 1)
        self.client = None

    def connect(self):
        self.client = ModbusTcpClient(self.ip, port=self.port, timeout=3)
        return self.client.connect()

    def read_tags(self, tags):
        if not self.client or not self.client.connected:
            if not self.connect():
                raise ConnectionError(f"Không kết nối được PLC tại {self.ip}:{self.port}")
        return read_modbus_tags(self.client, self.slave_id, tags)

    def close(self):
        if self.client:
            self.client.close()
