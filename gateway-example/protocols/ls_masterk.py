# ============================================================
# protocols/ls_masterk.py
# PART 1A
# ============================================================

import re
import time
import serial

ENQ = 0x05
ACK = 0x06
NAK = 0x15
EOT = 0x04
ETX = 0x03


class LSMasterKReader:

    def __init__(self, connection):

        self.port = connection["port"]

        self.baudrate = connection.get("baudrate", 9600)

        self.parity = connection.get("parity", "E")

        self.stopbits = connection.get("stopbits", 1)

        self.bytesize = connection.get("bytesize", 8)

        self.timeout = connection.get("timeout", 2)

        station = connection.get("station", "01")

        if isinstance(station, str):
            self.station = station.upper()
        else:
            self.station = "%02X" % station

        self.ser = None

    # -----------------------------------------------------

    def connect(self):

        if self.ser and self.ser.is_open:
            return

        self.ser = serial.Serial(

            port=self.port,

            baudrate=self.baudrate,

            parity=self.parity,

            stopbits=self.stopbits,

            bytesize=self.bytesize,

            timeout=self.timeout

        )

        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    # -----------------------------------------------------

    def close(self):

        if self.ser:

            self.ser.close()

            self.ser = None

    # -----------------------------------------------------

    def _bcc(self, frame):

        bcc = sum(frame) & 0xFF

        return ("%02X" % bcc).encode()

    # -----------------------------------------------------

    def _send(self, body):

        frame = bytearray()

        frame.append(ENQ)

        frame.extend(body)

        frame.append(EOT)

        frame.extend(self._bcc(frame))

        print("=" * 60)
        print("TX ASCII :", bytes(frame))
        print("TX HEX   :", bytes(frame).hex(" "))

        self.ser.reset_input_buffer()

        self.ser.write(frame)

        self.ser.flush()

    # -----------------------------------------------------

    def _recv(self):

        rx = bytearray()

        t = time.time()

        while True:

            if self.ser.in_waiting:

                rx.extend(self.ser.read(self.ser.in_waiting))

                if ETX in rx:
                    break

            if time.time() - t > self.timeout:
                break

            time.sleep(0.01)

        rx = bytes(rx)

        print("RX ASCII :", rx)

        print("RX HEX   :", rx.hex(" "))

        return rx

    # -----------------------------------------------------

    def _device(self, text):

        text = text.upper().replace("%", "").strip()

        m = re.match(r"([PMKLTCFDS])(\d+)", text)

        if not m:
            raise ValueError(text)

        dev = m.group(1)

        addr = int(m.group(2))

        if dev in ("P","M","K","L","T","C","F"):

            return "%%%sX%03d" % (dev, addr)

        if dev in ("D","S"):

            return "%%%sW%03d" % (dev, addr)

        raise ValueError(text)

# ===================== END PART 1A =====================
# ============================================================
# protocols/ls_masterk.py
# PART 1B
# Frame Builder (RSS / RSB / WSS / WSB)
# ============================================================

    # -----------------------------------------------------
    # ASCII HEX
    # -----------------------------------------------------

    def _hex2(self, value):

        return ("%02X" % value).encode("ascii")

    # -----------------------------------------------------
    # RSS
    # Individual Read
    # -----------------------------------------------------

    def _frame_rss(self, devices):

        body = bytearray()

        body.extend(self.station.encode())

        body.extend(b"r")

        body.extend(b"SS")

        body.extend(self._hex2(len(devices)))

        for dev in devices:

            name = self._device(dev)

            body.extend(self._hex2(len(name)))

            body.extend(name.encode())

        return bytes(body)

    # -----------------------------------------------------
    # RSB
    # Continuous Read
    # -----------------------------------------------------

    def _frame_rsb(self, device, count):

        name = self._device(device)

        body = bytearray()

        body.extend(self.station.encode())

        body.extend(b"r")

        body.extend(b"SB")

        body.extend(self._hex2(len(name)))

        body.extend(name.encode())

        body.extend(self._hex2(count))

        return bytes(body)

    # -----------------------------------------------------
    # WSS
    # Individual Write
    # -----------------------------------------------------

    def _frame_wss(self, items):

        body = bytearray()

        body.extend(self.station.encode())

        body.extend(b"w")

        body.extend(b"SS")

        body.extend(self._hex2(len(items)))

        for device, value in items:

            name = self._device(device)

            body.extend(self._hex2(len(name)))

            body.extend(name.encode())

            # Bit Device
            if name[2] == "X":

                if int(value):
                    body.extend(b"01")
                else:
                    body.extend(b"00")

            # Word Device
            else:

                body.extend(
                    ("%04X" % (int(value) & 0xFFFF)).encode()
                )

        return bytes(body)

    # -----------------------------------------------------
    # WSB
    # Continuous Write
    # -----------------------------------------------------

    def _frame_wsb(self, device, values):

        name = self._device(device)

        body = bytearray()

        body.extend(self.station.encode())

        body.extend(b"w")

        body.extend(b"SB")

        body.extend(self._hex2(len(name)))

        body.extend(name.encode())

        body.extend(self._hex2(len(values)))

        for value in values:

            body.extend(
                ("%04X" % (int(value) & 0xFFFF)).encode()
            )

        return bytes(body)

    # -----------------------------------------------------
    # Request
    # -----------------------------------------------------

    def _request(self, body):

        self._send(body)

        return self._recv()

# ===================== END PART 1B =====================
