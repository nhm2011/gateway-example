import socket
import struct


class OmronFinsReader:
    """
    Omron FINS (Factory Interface Network Service) Protocol qua Ethernet (UDP).
    Dùng cho PLC Omron kết nối qua mạng LAN — không cần bộ chuyển đổi trung gian.

    Tương thích:
        CP1L-E, CP1H-E (có cổng Ethernet tích hợp)
        CJ2M, CJ2H (module CJ1W-ETN21)
        CS1 (module CS1W-ETN21)
        NX1P2, NX102 (cổng Ethernet tích hợp)
        NJ Series (cổng Ethernet tích hợp)

    Không dùng được cho:
        CP1L không có suffix -E (chỉ có RS232/USB)
        → Cần cắm thêm module CP1W-CIF41 hoặc dùng modbus_rtu qua RS232

    Địa chỉ vùng nhớ (address):
        "D100"   → DM area, word 100 (vùng nhớ dữ liệu chính, phổ biến nhất)
        "D100F"  → DM area, word 100+101 ghép float32
        "W100"   → WR area, word 100 (work area)
        "H100"   → HR area, word 100 (holding relay)
        "CIO100" → CIO area (I/O chính)

    Connection config:
        {
            "ip": "192.168.1.10",
            "port": 9600,           # mặc định FINS/UDP là 9600
            "dest_node": 10,        # FINS node của PLC (= octet cuối của IP, vd: 192.168.1.10 → node=10)
            "src_node": 100         # FINS node của máy tính gateway (đặt tuỳ ý, không trùng PLC)
        }

    Lưu ý cấu hình trong CX-Programmer / Sysmac Studio:
        Vào Settings → Built-in Ethernet Port Settings → đặt IP, subnet
        FINS node thường tự động = octet cuối của IP
    """

    MEMORY_AREAS = {
        "CIO": (0x30, 0xB0),  # (word_code, bit_code)
        "W":   (0x31, 0xB1),
        "H":   (0x32, 0xB2),
        "A":   (0x33, 0xB3),
        "D":   (0x82, 0x02),
    }

    def __init__(self, connection):
        self.ip = connection["ip"]
        self.port = connection.get("port", 9600)
        self.dest_node = connection.get("dest_node", int(self.ip.split(".")[-1]))
        self.src_node = connection.get("src_node", 100)
        self.timeout = connection.get("timeout", 3)
        self.sock = None

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(self.timeout)

    def _build_fins_frame(self, memory_code, start_addr, count):
        """Tạo FINS command 0101 (Memory Area Read)."""
        header = bytes([
            0x80, 0x00,                      # ICF, RSV
            0x02,                            # GCT (gateway count)
            0x00, self.dest_node, 0x00,      # dest network, node, unit
            0x00, self.src_node, 0x00,       # src network, node, unit
            0x00, 0x00,                      # service ID (sequential)
        ])
        command = bytes([0x01, 0x01])        # command: Memory Area Read
        body = bytes([memory_code]) + struct.pack(">HB", start_addr, 0x00) + struct.pack(">H", count)
        return header + command + body

    def _parse_address(self, address_str):
        address_str = address_str.upper().strip()
        is_float = address_str.endswith("F")
        if is_float:
            address_str = address_str[:-1]
        for area in sorted(self.MEMORY_AREAS.keys(), key=len, reverse=True):
            if address_str.startswith(area):
                addr = int(address_str[len(area):])
                return area, addr, is_float
        raise ValueError(f"Địa chỉ không hợp lệ: '{address_str}'. Ví dụ đúng: D100, W10, CIO0")

    def read_tags(self, tags):
        if not self.sock:
            self.connect()
        values = {}
        for tag in tags:
            try:
                area, addr, is_float = self._parse_address(tag["address"])
                mem_code = self.MEMORY_AREAS[area][0]
                data_type = tag.get("data_type", "int16")
                scale = tag.get("scale") or 1
                count = 2 if (data_type == "float32" or is_float) else 1

                frame = self._build_fins_frame(mem_code, addr, count)
                self.sock.sendto(frame, (self.ip, self.port))
                resp, _ = self.sock.recvfrom(1024)

                if len(resp) < 14:
                    raise IOError("Phản hồi FINS quá ngắn")
                end_code = struct.unpack(">H", resp[12:14])[0]
                if end_code != 0:
                    raise IOError(f"PLC trả về lỗi FINS: 0x{end_code:04X}")

                data = resp[14:]
                if count == 2 or is_float or data_type == "float32":
                    w0, w1 = struct.unpack(">HH", data[:4])
                    value = round(struct.unpack(">f", struct.pack(">HH", w0, w1))[0], 4)
                else:
                    raw = struct.unpack(">H", data[:2])[0]
                    if data_type == "int16" and raw > 32767:
                        raw -= 65536
                    value = round(raw / scale, 4)

                values[tag["tag_key"]] = value
            except Exception as e:
                print(f"[fins] lỗi đọc tag '{tag['tag_key']}' ({tag.get('address')}): {e}")
        return values

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
