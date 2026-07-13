# protocols/ls_frame.py

from dataclasses import dataclass

ENQ = 0x05
ACK = 0x06
NAK = 0x15
EOT = 0x04
ETX = 0x03


def ascii_hex(value: int, width: int = 2) -> str:
    """
    1  -> "01"
    10 -> "0A"
    16 -> "10"
    """
    return f"{value:0{width}X}"


def calc_bcc(data: bytes) -> bytes:
    """
    Dedicated Protocol BCC

    cộng tất cả byte từ ENQ -> EOT (hoặc ETX)
    lấy byte thấp
    đổi sang ASCII HEX
    """

    s = sum(data) & 0xFF
    return f"{s:02X}".encode("ascii")


@dataclass
class Frame:

    station: int = 1

    def station_ascii(self) -> bytes:
        return ascii_hex(self.station).encode()

    def make(self,
             cmd: str,
             cmd_type: str,
             payload: bytes = b"") -> bytes:

        body = (
            self.station_ascii()
            + cmd.encode()
            + cmd_type.encode()
            + payload
        )

        frame = bytes([ENQ]) + body + bytes([EOT])

        return frame + calc_bcc(frame)


class RSSFrame(Frame):

    def build(self, devices):

        """
        devices

        [
            "%MX000",
            "%DW100"
        ]
        """

        payload = ascii_hex(len(devices)).encode()

        for dev in devices:

            payload += ascii_hex(len(dev)).encode()

            payload += dev.encode()

        return self.make("r", "SS", payload)


class RSBFrame(Frame):

    def build(self,
              device: str,
              count: int):

        payload = (
            ascii_hex(len(device)).encode()
            + device.encode()
            + ascii_hex(count).encode()
        )

        return self.make("r", "SB", payload)


class WSSFrame(Frame):

    def build(self,
              items):

        """
        items

        [
            ("%MX000","01"),
            ("%DW100","1234")
        ]
        """

        payload = ascii_hex(len(items)).encode()

        for dev, value in items:

            payload += ascii_hex(len(dev)).encode()

            payload += dev.encode()

            payload += value.encode()

        return self.make("w", "SS", payload)


class WSBFrame(Frame):

    def build(self,
              device,
              values):

        """
        values

        ["1234","5678"]
        """

        data = "".join(values)

        payload = (
            ascii_hex(len(device)).encode()
            + device.encode()
            + ascii_hex(len(values)).encode()
            + data.encode()
        )

        return self.make("w", "SB", payload)


if __name__ == "__main__":

    f = RSSFrame(1)

    tx = f.build(["%MW100"])

    print(tx)

    print(tx.hex(" "))