import re
import struct
from snap7.client import Client


class S7Reader:
    """PLC Siemens S7-300/400/1200/1500 qua giao thức S7 gốc — nhanh hơn và ổn định hơn
    so với đi qua OPC UA gateway trung gian, nhưng cần cài thêm thư viện hệ thống libsnap7
    (xem ghi chú cài đặt trong README của thư mục gateway-example).

    Định dạng địa chỉ (address) khai báo trong tag:
        "DB1.DBD0"    -> Double word tại DB1, offset byte 0 (dùng cho float32 hoặc số nguyên 32-bit)
        "DB1.DBW2"    -> Word tại DB1, offset byte 2 (dùng cho int16/uint16)
        "DB1.DBX4.0"  -> Bit tại DB1, offset byte 4, bit thứ 0 (dùng cho trạng thái ON/OFF)

    Các con số này lấy từ bảng khai báo biến (Tag table / DB) trong TIA Portal hoặc Step7.
    """

    ADDRESS_RE = re.compile(r"^DB(\d+)\.DB([DWX])(\d+)(?:\.(\d))?$", re.IGNORECASE)

    def __init__(self, connection):
        self.ip = connection["ip"]
        self.rack = connection.get("rack", 0)
        self.slot = connection.get("slot", 1)
        self.client = None

    def connect(self):
        self.client = Client()
        self.client.connect(self.ip, self.rack, self.slot)

    def read_tags(self, tags):
        if not self.client or not self.client.get_connected():
            self.connect()

        values = {}
        for tag in tags:
            try:
                match = self.ADDRESS_RE.match(tag["address"].strip())
                if not match:
                    print(f"[s7] địa chỉ không hợp lệ cho tag '{tag['tag_key']}': '{tag['address']}' "
                          f"(đúng định dạng phải là vd: DB1.DBD0, DB1.DBW2, DB1.DBX4.0)")
                    continue

                db_number, area, offset, bit = match.groups()
                db_number, offset = int(db_number), int(offset)
                data_type = tag.get("data_type", "int16")
                scale = tag.get("scale") or 1
                area = area.upper()

                if area == "X":
                    raw = self.client.db_read(db_number, offset, 1)
                    value = bool((raw[0] >> int(bit or 0)) & 1)
                elif area == "W":
                    raw = self.client.db_read(db_number, offset, 2)
                    fmt = ">h" if data_type == "int16" else ">H"
                    value = round(struct.unpack(fmt, raw)[0] / scale, 4)
                elif area == "D":
                    raw = self.client.db_read(db_number, offset, 4)
                    if data_type == "float32":
                        value = round(struct.unpack(">f", raw)[0], 4)
                    else:
                        value = round(struct.unpack(">i", raw)[0] / scale, 4)
                else:
                    continue

                values[tag["tag_key"]] = value
            except Exception as e:
                print(f"[s7] lỗi đọc tag '{tag['tag_key']}': {e}")

        return values

    def close(self):
        if self.client:
            try:
                self.client.disconnect()
            except Exception:
                pass
