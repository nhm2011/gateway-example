import socket
import struct


class MitsubishiMcReader:
    """
    Mitsubishi MC Protocol (MELSEC Communication Protocol) - Frame 3E.
    Dùng cho PLC Mitsubishi qua cổng Ethernet (không cần Modbus gateway trung gian).

    Tương thích:
        FX5U, FX5UC (module Ethernet tích hợp)
        Q Series, L Series (module QJ71E71, LJ71E71)
        iQ-R Series (module RJ71EN71)
        iQ-F FX5 Series

    Không dùng được cho:
        FX3U, FX3G, FX2N (chỉ có RS232/RS485, cần dùng modbus_rtu)
        → Với FX3 trở về: cần kết hợp với adapter FX3U-ENET-ADP hoặc module FX3U-ENET

    Địa chỉ vùng nhớ (address format) trong config tag:
        "D100"   → Data register D100 (số nguyên 16-bit, phổ biến nhất)
        "D100F"  → Data register D100 dạng float32 (2 word ghép)
        "M100"   → Bit M100 (coil nội bộ)
        "X0"     → Input X0 (hex: X0=0, X10=16...)
        "Y0"     → Output Y0
        "W100"   → Link register W100 (CC-Link)

    Connection config:
        {
            "ip": "192.168.1.10",
            "port": 5010,              # mặc định Mitsubishi là 5010, có thể đổi trong GX Works
            "station": 0,              # Network station number, thường là 0
            "pc": 255                  # PC number, thường là 255
        }
    """

    # Từ điển loại vùng nhớ → subcommand byte
    DEVICE_CODES = {
        "D": 0xA8,  "W": 0xB4,  "R": 0xAF,   # word registers
        "M": 0x90,  "L": 0x92,  "F": 0x93,   # bit devices (coils)
        "X": 0x9C,  "Y": 0x9D,               # I/O
        "B": 0xA0,  "SB": 0xA1,              # link relays
    }

    def __init__(self, connection):
        self.ip = connection["ip"]
        self.port = connection.get("port", 5010)
        self.station = connection.get("station", 0)
        self.pc = connection.get("pc", 255)
        self.timeout = connection.get("timeout", 3)
        self.sock = None

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        try:
            self.sock.connect((self.ip, self.port))
        except Exception as e:
            self.sock = None
            raise ConnectionError(
                f"Không kết nối được PLC Mitsubishi tại {self.ip}:{self.port}. "
                f"Kiểm tra: IP đúng không, port 5010 có được mở trong cấu hình GX Works không, "
                f"firewall PLC có chặn không. Lỗi: {e}"
            )

    def _parse_address(self, address_str):
        """Phân tích địa chỉ như 'D100', 'M10', 'X1F' → (device_code, address_int)"""
        address_str = address_str.upper().strip()
        for code in sorted(self.DEVICE_CODES.keys(), key=len, reverse=True):
            if address_str.startswith(code):
                rest = address_str[len(code):]
                # X, Y dùng hệ hex; các loại khác dùng decimal
                base = 16 if code in ("X", "Y", "B") else 10
                return code, int(rest, base)
        raise ValueError(f"Địa chỉ không nhận dạng được: '{address_str}'. Ví dụ đúng: D100, M10, X0, Y0")

    def _build_read_request(self, device_code, start_addr, count, is_word=True):
        """Tạo MC Protocol 3E frame để đọc vùng nhớ."""
        subcommand = 0x0000 if is_word else 0x0001
        dev_code = self.DEVICE_CODES[device_code]

        data = struct.pack("<HH", 0x0401, subcommand)           # command: batch read
        data += struct.pack("<I", start_addr)[:3]                # start address (3 bytes LE)
        data += bytes([dev_code])                                # device code
        data += struct.pack("<H", count)                         # number of points

        header = bytes([
            0x50, 0x00,              # subheader
            self.station, 0x00,      # network/station
            0xFF,                    # PC number
            0xFF, 0x03,              # request destination (CPU)
            0x00, 0x00,              # monitoring timer
        ])
        length = struct.pack("<H", len(data))
        return header + length + data

    def _read_word(self, device_code, addr, count=1):
        req = self._build_read_request(device_code, addr, count, is_word=True)
        self.sock.sendall(req)
        resp = self.sock.recv(1024)
        if len(resp) < 11:
            raise IOError("Phản hồi quá ngắn từ PLC")
        end_code = struct.unpack("<H", resp[9:11])[0]
        if end_code != 0:
            raise IOError(f"PLC trả về lỗi: 0x{end_code:04X}")
        words = []
        for i in range(count):
            words.append(struct.unpack("<H", resp[11 + i*2: 13 + i*2])[0])
        return words

    def read_tags(self, tags):
        if not self.sock:
            self.connect()
        values = {}
        for tag in tags:
            try:
                address = tag["address"].upper().strip()
                is_float = address.endswith("F")
                if is_float:
                    address = address[:-1]
                device_code, addr_int = self._parse_address(address)
                data_type = tag.get("data_type", "int16")
                scale = tag.get("scale") or 1

                if data_type == "float32" or is_float:
                    words = self._read_word(device_code, addr_int, 2)
                    raw = struct.pack("<HH", words[0], words[1])
                    value = round(struct.unpack("<f", raw)[0], 4)
                else:
                    words = self._read_word(device_code, addr_int, 1)
                    raw = words[0]
                    if data_type == "int16" and raw > 32767:
                        raw -= 65536
                    value = round(raw / scale, 4)

                values[tag["tag_key"]] = value
            except Exception as e:
                print(f"[mc] lỗi đọc tag '{tag['tag_key']}' ({tag.get('address')}): {e}")
        return values

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
