import struct


def decode_float32(registers, byteorder="big"):
    if byteorder == "big":
        raw = struct.pack(">HH", registers[0], registers[1])
        return struct.unpack(">f", raw)[0]
    raw = struct.pack("<HH", registers[1], registers[0])
    return struct.unpack("<f", raw)[0]


def decode_int32(registers, signed=True, word_order="big"):
    """
    word_order:
        "big"    -> registers[0] là word cao, registers[1] là word thấp (ABCD)
        "little" -> registers[0] là word thấp, registers[1] là word cao (CDAB)
    Mỗi hãng PLC ghép word 32-bit khác nhau, cần test thực tế trên từng loại
    (LS XGB, K7M, FX3U/FX3S...) rồi chọn word_order phù hợp qua tag config.
    """
    if word_order == "big":
        raw = struct.pack(">HH", registers[0], registers[1])
    else:
        raw = struct.pack(">HH", registers[1], registers[0])
    fmt = ">i" if signed else ">I"
    return struct.unpack(fmt, raw)[0]


def encode_int32(value, signed=True, word_order="big"):
    """Trả về list 2 register (16-bit) theo word_order tương ứng."""
    fmt = ">i" if signed else ">I"
    raw = struct.pack(fmt, int(value))
    hi, lo = struct.unpack(">HH", raw)
    if word_order == "big":
        return [hi, lo]
    return [lo, hi]


def _call(client, method, address, count=1, slave_id=1):
    """Gọi method với mọi tổ hợp tham số có thể, cho mọi version pymodbus."""
    fn = getattr(client, method)
    last_err = None
    for kw in ("slave", "unit", "device_id"):
        try:
            return fn(address, count=count, **{kw: slave_id})
        except TypeError as e:
            last_err = e
            continue
    try:
        return fn(address, count=count)
    except TypeError as e:
        last_err = e
    raise last_err


def _write(client, method, address, value, slave_id=1):
    fn = getattr(client, method)
    last_err = None
    for kw in ("slave", "unit", "device_id"):
        try:
            return fn(address, value, **{kw: slave_id})
        except TypeError as e:
            last_err = e
            continue
    try:
        return fn(address, value)
    except TypeError as e:
        last_err = e
    raise last_err


def read_modbus_tags(client, slave_id, tags):
    """
    data_type hỗ trợ:
        int16 / uint16 / float32 — register thường
        coil    — bit coil (M, Y...) qua FC01
        bit:N   — bit thứ N trong 1 word register (D)
    """
    values = {}
    for tag in tags:
        try:
            address = int(str(tag["address"]).split(":")[0])
            data_type = tag.get("data_type", "int16")
            scale = tag.get("scale") or 1

            if data_type == "coil":
                r = _call(client, "read_coils", address, 1, slave_id)
                if not r.isError():
                    values[tag["tag_key"]] = int(r.bits[0])
                else:
                    print(f"[modbus] lỗi đọc coil '{tag['tag_key']}' addr={address}")
                continue

            if data_type.startswith("bit:"):
                bit_pos = int(data_type.split(":")[1])
                r = _call(client, "read_holding_registers", address, 1, slave_id)
                if r.isError():
                    r = _call(client, "read_input_registers", address, 1, slave_id)
                if not r.isError():
                    values[tag["tag_key"]] = int((r.registers[0] >> bit_pos) & 1)
                else:
                    print(f"[modbus] lỗi đọc D bit '{tag['tag_key']}' addr={address}")
                continue

            count = 2 if data_type in ("float32", "int32", "uint32") else 1
            r = _call(client, "read_holding_registers", address, count, slave_id)
            if r.isError():
                r = _call(client, "read_input_registers", address, count, slave_id)
            if r.isError():
                print(f"[modbus] lỗi đọc register '{tag['tag_key']}' addr={address}")
                continue

            if data_type == "float32":
                value = decode_float32(r.registers)
            elif data_type in ("int32", "uint32"):
                word_order = tag.get("word_order", "big")
                raw = decode_int32(
                    r.registers,
                    signed=(data_type == "int32"),
                    word_order=word_order,
                )
                value = raw / scale
            else:
                raw = r.registers[0]
                if data_type == "int16" and raw > 32767:
                    raw -= 65536
                value = raw / scale
            values[tag["tag_key"]] = round(value, 4)

        except Exception as e:
            print(f"[modbus] lỗi tag '{tag.get('tag_key')}': {e}")
    return values


def write_modbus_tag(client, slave_id, address, value, data_type="int16", scale=1, word_order="big"):
    if data_type == "coil":
        r = _write(client, "write_coil", address, bool(int(float(value))), slave_id)
        if r.isError():
            raise IOError(f"write_coil lỗi addr={address}: {r}")
        return r

    if data_type.startswith("bit:"):
        bit_pos = int(data_type.split(":")[1])
        r = _call(client, "read_holding_registers", address, 1, slave_id)
        if r.isError():
            raise IOError(f"Không đọc được D{address} để sửa bit")
        word = r.registers[0]
        if int(float(value)):
            word |= (1 << bit_pos)
        else:
            word &= ~(1 << bit_pos)
        word &= 0xFFFF
        r2 = _write(client, "write_register", address, word, slave_id)
        if r2.isError():
            raise IOError(f"write_register D{address} bit {bit_pos} lỗi: {r2}")
        return r2

    if data_type == "float32":
        packed = struct.pack(">f", float(value))
        regs = [(packed[0] << 8) | packed[1], (packed[2] << 8) | packed[3]]
        r = _write(client, "write_registers", address, regs, slave_id)
        if r.isError():
            raise IOError(f"write_registers float32 addr={address}: {r}")
        return r

    if data_type in ("int32", "uint32"):
        regs = encode_int32(
            round(float(value) * scale),
            signed=(data_type == "int32"),
            word_order=word_order,
        )
        r = _write(client, "write_registers", address, regs, slave_id)
        if r.isError():
            raise IOError(f"write_registers {data_type} addr={address}: {r}")
        return r

    raw = int(float(value) * scale) & 0xFFFF
    r = _write(client, "write_register", address, raw, slave_id)
    if r.isError():
        raise IOError(f"write_register addr={address}: {r}")
    return r


def write_modbus_register(client, slave_id, address, value, data_type="int16", scale=1, word_order="big"):
    return write_modbus_tag(client, slave_id, address, value, data_type, scale, word_order)
