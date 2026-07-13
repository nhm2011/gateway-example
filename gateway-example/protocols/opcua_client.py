from opcua import Client as OpcUaClientLib


class OpcUaReader:
    """Dùng cho thiết bị/PLC hỗ trợ OPC UA (chuẩn công nghiệp đa hãng, phổ biến
    với Siemens TIA Portal, Beckhoff, WinCC, hoặc qua OPC UA server trung gian
    như KEPServerEX). Mỗi tag dùng Node ID thay vì địa chỉ thanh ghi,
    vd: "ns=2;i=2" hoặc "ns=2;s=Channel1.Device1.Tag1" - lấy từ phần mềm cấu hình OPC server."""

    def __init__(self, connection):
        self.endpoint = connection["endpoint"]  # vd: "opc.tcp://192.168.1.20:4840"
        self.username = connection.get("username")
        self.password = connection.get("password")
        self.client = None

    def connect(self):
        self.client = OpcUaClientLib(self.endpoint)
        if self.username:
            self.client.set_user(self.username)
            self.client.set_password(self.password)
        self.client.connect()

    def read_tags(self, tags):
        if not self.client:
            self.connect()
        values = {}
        for tag in tags:
            try:
                node = self.client.get_node(tag["address"])
                raw = node.get_value()
                scale = tag.get("scale") or 1
                if isinstance(raw, (int, float)):
                    values[tag["tag_key"]] = round(raw / scale, 4)
                else:
                    values[tag["tag_key"]] = raw
            except Exception as e:
                print(f"[opcua] lỗi đọc tag '{tag['tag_key']}' (node {tag['address']}): {e}")
        return values

    def close(self):
        if self.client:
            try:
                self.client.disconnect()
            except Exception:
                pass
