"""
Gateway đa giao thức - chạy tại nhà máy khách hàng (Raspberry Pi, mini PC...).
Đọc dữ liệu từ nhiều thiết bị (Modbus TCP / Modbus RTU / OPC UA / S7) cùng lúc,
gửi lên VPS qua MQTT. Nhận lệnh điều khiển từ VPS và ghi vào PLC.

Cài đặt:
    pip install -r requirements.txt

Chạy:
    python universal_gateway.py config.json 
"""

import sys
import json
import time
import struct

import paho.mqtt.client as mqtt

from protocols.modbus_tcp import ModbusTcpReader
from protocols.modbus_rtu import ModbusRtuReader, ModbusRs232Reader
from protocols.opcua_client import OpcUaReader
from protocols.s7 import S7Reader
from protocols.mitsubishi_mc import MitsubishiMcReader
from protocols.omron_fins import OmronFinsReader
from protocols.delta_dvp import DeltaDvpReader
from protocols.ls_xgb import LsXgbReader
from protocols.mitsubishi_fx_cl import MitsubishiFxClReader

READER_CLASSES = {
    # Modbus chuẩn
    "modbus_tcp":   ModbusTcpReader,    # Modbus TCP/IP - PLC có cổng Ethernet
    "modbus_rtu":   ModbusRtuReader,    # Modbus RTU qua RS485 - biến tần, đồng hồ điện, cảm biến
    "modbus_rs232": ModbusRs232Reader,  # Modbus RTU qua RS232 - PLC đời cũ, khoảng cách ngắn

    # Giao thức độc quyền qua Ethernet
    "opcua":          OpcUaReader,       # OPC UA - chuẩn đa hãng, Siemens TIA Portal, Beckhoff
    "s7":             S7Reader,          # Siemens S7 gốc - S7-1200/1500/300/400
    "mitsubishi_mc":  MitsubishiMcReader,# Mitsubishi MC Protocol - FX5U, Q/L/iQ-R series
    "omron_fins":     OmronFinsReader,   # Omron FINS/TCP - CP1L-E, CJ2, NX/NJ series
    "delta_dvp":      DeltaDvpReader,    # Delta DVP - ES3/EH3 Ethernet, hoặc RTU qua RS485

    # PLC hãng cụ thể qua Modbus với tham số mặc định đặc biệt
    "ls_xgb":         LsXgbReader,       # LS/LG XGB/XGI - parity Even mặc định

    # Mitsubishi FX qua board 485-BD thường (không MB) - Computer Link Format 1
    "mitsubishi_fx_cl": MitsubishiFxClReader,
}


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_mqtt_client(mqtt_cfg, client_id, status_topic):
    try:
        # paho-mqtt >= 2.0: dùng CallbackAPIVersion mới
        from paho.mqtt.enums import CallbackAPIVersion
        client = mqtt.Client(client_id=client_id, callback_api_version=CallbackAPIVersion.VERSION2)
    except ImportError:
        # paho-mqtt < 2.0: dùng API cũ
        client = mqtt.Client(client_id=client_id)
    client.username_pw_set(mqtt_cfg["username"], mqtt_cfg["password"])
    # payload dạng JSON để phân biệt lý do offline: "gateway" (mất kết nối MQTT/Raspberry Pi)
    # hay "plc" (gateway vẫn sống nhưng không đọc được PLC, xem vòng lặp poll bên dưới)
    client.will_set(status_topic, payload=json.dumps({"online": False, "reason": "gateway"}), retain=True)
    if mqtt_cfg.get("use_tls"):
        client.tls_set()
    client.connect(mqtt_cfg["host"], mqtt_cfg.get("port", 1883), keepalive=30)
    client.loop_start()
    client.publish(status_topic, json.dumps({"online": True, "reason": "gateway"}), retain=True)
    return client


def write_tag(reader, tag_cfg, value):
    """Ghi giá trị vào PLC qua giao thức tương ứng."""
    protocol = type(reader).__name__

    if "ModbusTcp" in protocol or "ModbusRtu" in protocol \
            or "LsXgb" in protocol or "DeltaDvp" in protocol:
        from protocols.modbus_common import write_modbus_tag
        # address có thể là "0" (số thường) — data_type quyết định FC nào được dùng
        # word_order quyết định thứ tự ghép 2 register cho int32/uint32 (mặc định "big")
        write_modbus_tag(
            reader.client, reader.slave_id,
            int(str(tag_cfg["address"]).split(":")[0]),
            value,
            tag_cfg.get("data_type", "int16"),
            tag_cfg.get("scale") or 1,
            tag_cfg.get("word_order", "big"),
        )

    elif "MitsubishiFxCl" in protocol:
        address = str(tag_cfg["address"]).upper()
        device_letter = address[0]
        number = int(address[1:])
        data_type = tag_cfg.get("data_type", "bit" if device_letter in ("M", "X", "Y", "S", "T", "C") else "int16")
        word_order = tag_cfg.get("word_order", "big")
        scale = tag_cfg.get("scale") or 1

        if data_type in ("bit", "coil"):
            reader.write_bit(device_letter, number, bool(value) if not isinstance(value, str) else value in ("1", "true", "True"))
        elif data_type in ("int32", "uint32"):
            raw = int(round(float(value) * scale)) & 0xFFFFFFFF
            hi, lo = (raw >> 16) & 0xFFFF, raw & 0xFFFF
            words = [hi, lo] if word_order == "big" else [lo, hi]
            reader.write_words(device_letter, number, words)
        elif data_type == "float32":
            raw = struct.unpack(">I", struct.pack(">f", float(value)))[0]
            hi, lo = (raw >> 16) & 0xFFFF, raw & 0xFFFF
            words = [hi, lo] if word_order == "big" else [lo, hi]
            reader.write_words(device_letter, number, words)
        else:  # int16 / uint16
            raw = int(round(float(value) * scale))
            reader.write_word(device_letter, number, raw)

    elif "OpcUa" in protocol:
        from opcua import ua
        node = reader.client.get_node(tag_cfg["address"])
        node.set_value(ua.DataValue(ua.Variant(float(value), ua.VariantType.Float)))

    elif "S7" in protocol:
        import re
        match = re.match(r"DB(\d+)\.DB([DWX])(\d+)(?:\.(\d))?", tag_cfg["address"], re.I)
        if not match:
            raise ValueError(f"Địa chỉ S7 không hợp lệ: {tag_cfg['address']}")
        db, area, offset, bit = match.groups()
        db, offset = int(db), int(offset)
        area = area.upper()
        if area == "W":
            raw = int(float(value)) & 0xFFFF
            reader.client.db_write(db, offset, bytes([raw >> 8, raw & 0xFF]))
        elif area == "D":
            packed = struct.pack(">f", float(value))
            reader.client.db_write(db, offset, packed)
        elif area == "X":
            byte_data = reader.client.db_read(db, offset, 1)
            b = int(bit or 0)
            if float(value):
                byte_data[0] |= (1 << b)
            else:
                byte_data[0] &= ~(1 << b)
            reader.client.db_write(db, offset, bytes(byte_data))
    else:
        raise NotImplementedError(f"Giao thức {protocol} chưa hỗ trợ ghi")


def make_cmd_handler(reader, tags_map, mqtt_client, ack_topic, device_key):
    """Tạo callback xử lý lệnh write từ server."""
    def on_message(client, userdata, msg):
        cmd_id = None
        try:
            cmd = json.loads(msg.payload.decode())
            cmd_id = cmd.get("cmd_id")
            tag_key = cmd.get("tag_key")
            value = cmd.get("value")

            tag_cfg = tags_map.get(tag_key)
            if not tag_cfg:
                raise ValueError(f"Tag '{tag_key}' không tồn tại trong cấu hình gateway")

            # Kết nối lại nếu cần
            if not getattr(reader, 'client', None) or not reader.client.connected:
                reader.connect()

            print(f"[{device_key}] LỆNH ĐIỀU KHIỂN: {tag_key} = {value}")
            write_tag(reader, tag_cfg, value)
            mqtt_client.publish(ack_topic, json.dumps({"cmd_id": cmd_id, "success": True}))
            print(f"[{device_key}] OK - lệnh {cmd_id} thực thi thành công")

        except Exception as e:
            print(f"[{device_key}] LỖI lệnh {cmd_id}: {e}")
            mqtt_client.publish(ack_topic, json.dumps({
                "cmd_id": cmd_id, "success": False, "error": str(e)
            }))
    return on_message


def setup_devices(cfg):
    """Mỗi thiết bị có 1 kết nối MQTT riêng để hỗ trợ Last-Will-Testament."""
    site_key = cfg["site_key"]
    devices = []

    for dcfg in cfg["devices"]:
        protocol = dcfg["protocol"]
        reader_cls = READER_CLASSES.get(protocol)
        if not reader_cls:
            print(f"[bỏ qua] thiết bị '{dcfg['device_key']}': giao thức '{protocol}' chưa được hỗ trợ")
            continue

        device_key = dcfg["device_key"]
        status_topic = f"gw/{site_key}/{device_key}/status"
        data_topic = f"gw/{site_key}/{device_key}/data"
        cmd_topic = f"gw/{site_key}/{device_key}/cmd"
        ack_topic = f"gw/{site_key}/{device_key}/cmd_ack"

        reader = reader_cls(dcfg["connection"])
        tags_map = {t["tag_key"]: t for t in dcfg["tags"]}

        mqtt_client = build_mqtt_client(cfg["mqtt"], f"gw_{site_key}_{device_key}", status_topic)
        mqtt_client.subscribe(cmd_topic)
        mqtt_client.on_message = make_cmd_handler(reader, tags_map, mqtt_client, ack_topic, device_key)

        devices.append({
            "key": device_key,
            "reader": reader,
            "tags": dcfg["tags"],
            "interval": dcfg.get("poll_interval", 5),
            "next_poll": 0,
            "mqtt": mqtt_client,
            "data_topic": data_topic,
            "status_topic": status_topic,
            "fail_threshold": dcfg.get("offline_after_failures", 3),
            "fail_count": 0,
            "reported_offline": False,
        })
        print(f"[sẵn sàng] {device_key} ({protocol}), {len(dcfg['tags'])} tag, "
              f"đọc mỗi {dcfg.get('poll_interval', 5)}s, hỗ trợ điều khiển: {any(t.get('writable') for t in dcfg['tags'])}")

    return devices


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    cfg = load_config(config_path)
    devices = setup_devices(cfg)

    if not devices:
        print("Không có thiết bị nào hợp lệ trong config.json. Dừng.")
        return

    print(f"Gateway đang chạy cho site '{cfg['site_key']}' — Ctrl+C để dừng.")

    try:
        while True:
            now = time.time()
            for dev in devices:
                if now < dev["next_poll"]:
                    continue
                dev["next_poll"] = now + dev["interval"]
                try:
                    values = dev["reader"].read_tags(dev["tags"])
                except Exception as e:
                    values = {}
                    print(f"[{dev['key']}] lỗi đọc: {e}")

                if values:
                    dev["mqtt"].publish(dev["data_topic"], json.dumps({"tags": values}))
                    print(f"[{dev['key']}] đã gửi: {values}")

                    # Vừa đọc được dữ liệu -> thiết bị chắc chắn đang sống, reset bộ đếm lỗi
                    dev["fail_count"] = 0
                    if dev["reported_offline"]:
                        dev["mqtt"].publish(
                            dev["status_topic"],
                            json.dumps({"online": True, "reason": "plc"}),
                            retain=True,
                        )
                        dev["reported_offline"] = False
                        print(f"[{dev['key']}] đã kết nối lại -> báo online")
                else:
                    # Không đọc được tag nào trong lần poll này (mất cáp, PLC tắt nguồn...)
                    dev["fail_count"] += 1
                    print(f"[{dev['key']}] không đọc được tag nào (lỗi liên tiếp: {dev['fail_count']}/{dev['fail_threshold']})")
                    if dev["fail_count"] >= dev["fail_threshold"] and not dev["reported_offline"]:
                        dev["mqtt"].publish(
                            dev["status_topic"],
                            json.dumps({"online": False, "reason": "plc"}),
                            retain=True,
                        )
                        dev["reported_offline"] = True
                        print(f"[{dev['key']}] MẤT KẾT NỐI PLC -> đã báo offline qua MQTT")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nĐang dừng gateway...")
        for dev in devices:
            dev["reader"].close()
            dev["mqtt"].loop_stop()


if __name__ == "__main__":
    main()
