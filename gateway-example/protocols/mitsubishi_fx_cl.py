"""
protocols/mitsubishi_fx_cl.py
Reader cho Mitsubishi FX3S/FX3G/FX3U dung board 485-BD thuong (khong MB)
qua giao thuc Computer Link - Dedicated Protocol Format 1.

connection config (trong config.json):
{
    "port": "COM5",           # hoac "/dev/ttyUSB0" tren Linux/Raspberry Pi
    "baudrate": 9600,
    "station": 0,
    "timeout": 1.0
}

tag config:
{
    "tag_key": "den_bao",
    "address": "M0",          # bit device: M, X, Y  |  word device: D
    "data_type": "bit",       # "bit" cho M/X/Y | "int16" cho D
    "scale": 1,               # (tuy chon) chia khi doc, nhan khi ghi
    "writable": true
}
"""
import serial
import threading
import time
import struct


def _calc_sum(data: bytes) -> bytes:
    s = sum(data) & 0xFF
    return f"{s:02X}".encode()


def _device_str(device: str, number: int) -> bytes:
    return f"{device}{number:04d}".encode()


BIT_DEVICES = ("M", "X", "Y", "S", "T", "C")


def _combine_words(hi: int, lo: int, signed: bool) -> int:
    raw = (hi << 16) | lo
    if signed and raw >= 0x80000000:
        raw -= 0x100000000
    return raw


def _split_dword(value: int):
    raw = value & 0xFFFFFFFF
    return (raw >> 16) & 0xFFFF, raw & 0xFFFF   # hi, lo


def _words_to_float(hi: int, lo: int) -> float:
    raw = (hi << 16) | lo
    return struct.unpack(">f", raw.to_bytes(4, "big"))[0]


def _float_to_words(value: float):
    raw = struct.unpack(">I", struct.pack(">f", value))[0]
    return (raw >> 16) & 0xFFFF, raw & 0xFFFF   # hi, lo


class _ClientStatus:
    """Wrapper nho de expose .connected, khop voi cach cmd_handler kiem tra reader.client.connected"""
    def __init__(self, reader):
        self._reader = reader

    @property
    def connected(self):
        return bool(self._reader.ser and self._reader.ser.is_open)


class MitsubishiFxClReader:
    def __init__(self, connection):
        self.port = connection["port"]
        self.baudrate = connection.get("baudrate", 9600)
        self.station = connection.get("station", 0)
        self.timeout = connection.get("timeout", 1.0)
        self.pc_no = b"FF"
        self.ser = None
        self.lock = threading.Lock()   # tranh thread poll va thread MQTT cmd dung chung serial cung luc
        self.client = _ClientStatus(self)   # de khop voi write_tag() / cmd_handler hien co
        self.connect()

    # ---------- Ket noi ----------

    def connect(self):
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception:
            pass
        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.SEVENBITS,
            parity=serial.PARITY_EVEN,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
        )

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()

    # ---------- Frame noi bo ----------

    def _send_write_cmd(self, cmd: bytes, payload: bytes, retries: int = 2) -> bool:
        station_hex = f"{self.station:02X}".encode()
        body = station_hex + self.pc_no + cmd + b"0" + payload
        frame = b"\x05" + body + _calc_sum(body)

        last_err = None
        with self.lock:
            for attempt in range(retries + 1):
                self.ser.reset_input_buffer()
                self.ser.write(frame)
                resp = self.ser.read(16)
                if resp[:1] == b"\x06":
                    return True
                elif resp[:1] == b"\x15":
                    err = resp[5:7].decode(errors="replace") if len(resp) >= 7 else "?"
                    last_err = RuntimeError(f"FX PLC tra ve NAK, ma loi: {err}")
                else:
                    last_err = TimeoutError(f"FX PLC khong phan hoi hop le: {resp!r}")
                if attempt < retries:
                    time.sleep(0.1)   # cho bus RS485 on dinh truoc khi thu lai
        raise last_err

    def _send_read_cmd(self, cmd: bytes, payload: bytes, expected_data_len: int) -> bytes:
        station_hex = f"{self.station:02X}".encode()
        body = station_hex + self.pc_no + cmd + b"0" + payload
        frame = b"\x05" + body + _calc_sum(body)
        with self.lock:
            self.ser.reset_input_buffer()
            self.ser.write(frame)
            resp = self.ser.read(1 + 2 + 2 + expected_data_len + 1 + 2)
        if resp[:1] == b"\x15":
            err = resp[5:7].decode(errors="replace") if len(resp) >= 7 else "?"
            raise RuntimeError(f"FX PLC tra ve NAK, ma loi: {err}")
        if resp[:1] != b"\x02":
            raise TimeoutError(f"FX PLC khong tra du lieu hop le: {resp!r}")
        return resp[5:5 + expected_data_len]

    # ---------- API bit ----------

    def write_bit(self, device: str, number: int, value: bool):
        payload = b"01" + _device_str(device, number) + (b"1" if value else b"0")
        return self._send_write_cmd(b"BT", payload)

    def read_bit(self, device: str, number: int) -> bool:
        payload = _device_str(device, number) + b"01"
        data = self._send_read_cmd(b"BR", payload, expected_data_len=1)
        return data == b"1"

    # ---------- API word ----------

    def write_word(self, device: str, number: int, value: int):
        payload = _device_str(device, number) + b"01" + f"{value & 0xFFFF:04X}".encode()
        return self._send_write_cmd(b"WW", payload)

    def read_word(self, device: str, number: int) -> int:
        payload = _device_str(device, number) + b"01"
        data = self._send_read_cmd(b"WR", payload, expected_data_len=4)
        return int(data.decode(), 16)

    def read_words(self, device: str, head_number: int, count: int):
        """Doc nhieu thanh ghi lien tuc, tra ve list[int] (unsigned 16-bit)."""
        payload = _device_str(device, head_number) + f"{count:02X}".encode()
        data = self._send_read_cmd(b"WR", payload, expected_data_len=count * 4)
        text = data.decode()
        return [int(text[i:i + 4], 16) for i in range(0, len(text), 4)]

    def write_words(self, device: str, head_number: int, values):
        """Ghi nhieu thanh ghi lien tuc (moi phan tu la unsigned 16-bit)."""
        n = len(values)
        payload = _device_str(device, head_number) + f"{n:02X}".encode()
        payload += "".join(f"{v & 0xFFFF:04X}" for v in values).encode()
        return self._send_write_cmd(b"WW", payload)

    # ---------- Interface chung cua gateway ----------

    def read_tags(self, tags):
        """Doc tung tag rieng le (an toan, don gian). Tag loi se bi bo qua, khong lam hong ca lo poll."""
        if not self.ser or not self.ser.is_open:
            self.connect()

        result = {}
        for tag in tags:
            address = str(tag["address"]).upper()
            device_letter = address[0]
            number = int(address[1:])
            data_type = tag.get("data_type", "bit" if device_letter in BIT_DEVICES else "int16")
            scale = tag.get("scale") or 1
            word_order = tag.get("word_order", "big")

            try:
                if data_type in ("bit", "coil"):
                    raw = self.read_bit(device_letter, number)
                    result[tag["tag_key"]] = bool(raw)

                elif data_type in ("int32", "uint32", "float32"):
                    w0, w1 = self.read_words(device_letter, number, 2)
                    hi, lo = (w0, w1) if word_order == "big" else (w1, w0)
                    if data_type == "float32":
                        value = _words_to_float(hi, lo)
                        decimals = tag.get("decimals", 2)   # mac dinh lam tron 2 chu so thap phan
                        value = round(value, decimals)
                    else:
                        value = _combine_words(hi, lo, signed=(data_type == "int32"))
                    result[tag["tag_key"]] = round(value / scale, 3) if scale != 1 else value

                else:  # int16 / uint16
                    raw = self.read_word(device_letter, number)
                    if data_type == "int16" and raw >= 0x8000:
                        raw -= 0x10000   # bu-2 -> so am
                    result[tag["tag_key"]] = round(raw / scale, 3) if scale != 1 else raw
            except Exception as e:
                print(f"[mitsubishi_fx_cl] lỗi đọc tag '{tag['tag_key']}' ({address}): {e}")
                # khong raise -> tag khac van duoc doc tiep tuc

        return result
