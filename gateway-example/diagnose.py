"""
CÔNG CỤ CHẨN ĐOÁN KẾT NỐI PLC
================================
Chạy script này để tìm đúng COM port, baudrate, parity trước khi cấu hình gateway.

Cách dùng:
    python diagnose.py                      # liệt kê tất cả cổng serial có sẵn
    python diagnose.py scan-modbus COM8     # quét tất cả slave ID 1-247 trên COM8
    python diagnose.py test-ls COM8         # test nhanh PLC LS XGB trên COM8
    python diagnose.py test-delta COM8      # test nhanh PLC Delta DVP trên COM8
    python diagnose.py test-tcp 192.168.1.10  # test Modbus TCP
"""

import sys
import json
import time


def list_ports():
    """Liệt kê tất cả cổng serial (COM/ttyUSB) có trên máy tính."""
    try:
        import serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            print("Không tìm thấy cổng serial nào.")
            print("Kiểm tra: đã cắm cáp USB chưa? Driver USB-Serial đã cài chưa?")
            return
        print(f"Tìm thấy {len(ports)} cổng serial:\n")
        for p in sorted(ports):
            print(f"  {p.device:12} | {p.description}")
            if p.manufacturer:
                print(f"               | Manufacturer: {p.manufacturer}")
        print("\nGợi ý:")
        print("  USB-RS232 (chip FTDI FT232):    thường là /dev/ttyUSB0 hoặc COMx")
        print("  USB-RS485 (chip CH340/CP2102):  thường là /dev/ttyUSB0 hoặc COMx")
        print("  PLC LS XGB qua cáp USB gốc:    chip Prolific PL2303 → COMx")
    except ImportError:
        print("Cần cài pyserial: pip install pyserial")


def test_modbus_serial(port, baudrate, parity, slave_id, timeout=3):
    """Thử đọc holding register 0 từ PLC."""
    from pymodbus.client import ModbusSerialClient
    client = ModbusSerialClient(
        port=port, baudrate=baudrate, parity=parity,
        stopbits=1, bytesize=8, timeout=timeout,
    )
    connected = client.connect()
    if not connected:
        print(f"  ✗ Không mở được cổng {port}")
        return False
    try:
        result = client.read_holding_registers(0, count=4, slave=slave_id)
        if result.isError():
            result2 = client.read_input_registers(0, count=4, slave=slave_id)
            if result2.isError():
                return False
            print(f"  ✓ Đọc được Input Register: {list(result2.registers)}")
        else:
            print(f"  ✓ Đọc được Holding Register: {list(result.registers)}")
        return True
    except Exception as e:
        print(f"  ✗ Lỗi: {e}")
        return False
    finally:
        client.close()


def scan_modbus(port):
    """Quét tất cả baudrate + parity + slave ID để tìm cấu hình đúng."""
    print(f"\n=== QUÉT CẤU HÌNH MODBUS RTU TRÊN {port} ===")
    print("Mỗi dấu chấm = 1 lần thử. Kiên nhẫn chờ...\n")

    combos = [
        (9600,  "E"), (9600,  "N"), (9600,  "O"),
        (19200, "E"), (19200, "N"), (38400, "E"),
        (38400, "N"), (115200,"N"),
    ]
    for slave_id in range(1, 5):    # thường slave ID 1-4
        for baudrate, parity in combos:
            sys.stdout.write(".")
            sys.stdout.flush()
            from pymodbus.client import ModbusSerialClient
            try:
                client = ModbusSerialClient(
                    port=port, baudrate=baudrate, parity=parity,
                    stopbits=1, bytesize=8, timeout=1,
                )
                if not client.connect():
                    client.close()
                    continue
                result = client.read_holding_registers(0, count=1, slave=slave_id)
                client.close()
                if not result.isError():
                    print(f"\n\n✓ TÌM THẤY! Cấu hình:")
                    print(f"    port:      {port}")
                    print(f"    baudrate:  {baudrate}")
                    print(f"    parity:    {parity}")
                    print(f"    stopbits:  1")
                    print(f"    slave_id:  {slave_id}")
                    print(f"\n  Dùng cấu hình này trong config.json của gateway.")
                    return
            except Exception:
                pass
    print("\n\nKhông tìm thấy cấu hình nào phù hợp.")
    print("Kiểm tra: PLC đã bật Modbus chưa? Cáp nối đúng chân TXD/RXD/GND chưa?")


def test_ls(port):
    """Test nhanh PLC LS XGB với cấu hình mặc định."""
    print(f"\n=== TEST PLC LS XGB TRÊN {port} ===")
    configs = [
        (9600, "E", 1),
        (9600, "N", 1),
        (19200, "E", 1),
        (19200, "N", 1),
    ]
    found = False
    for baud, parity, slave in configs:
        print(f"Thử: baud={baud}, parity={parity}, slave={slave}... ", end="")
        if test_modbus_serial(port, baud, parity, slave):
            print(f"\n✓ Cấu hình đúng cho LS XGB:")
            print(f'  "port": "{port}", "baudrate": {baud}, "parity": "{parity}", "slave_id": {slave}')
            print(f'\n  Lưu ý: Đảm bảo đã bật Modbus trong XG5000 và đóng XG5000 trước khi chạy gateway!')
            found = True
            break
        print("không đọc được")
    if not found:
        print("\n✗ Không kết nối được LS XGB.")
        print("Kiểm tra:")
        print("  1. Đã vào XG5000 → PLC Parameters → Comm. Parameters → bật Modbus Slave chưa?")
        print("  2. Đã đóng XG5000 chưa? (XG5000 đang mở sẽ chiếm cổng COM)")
        print("  3. Parity trong XG5000 đặt là gì? (mặc định Even)")
        print(f"  4. Cổng COM đúng không? Chạy: python diagnose.py  để xem danh sách")


def test_delta(port):
    """Test nhanh PLC Delta DVP."""
    print(f"\n=== TEST PLC DELTA DVP TRÊN {port} ===")
    configs = [
        (9600, "E", 1),
        (9600, "N", 1),
        (9600, "O", 1),
    ]
    for baud, parity, slave in configs:
        print(f"Thử: baud={baud}, parity={parity}, slave={slave}... ", end="")
        if test_modbus_serial(port, baud, parity, slave):
            print(f"\n✓ Cấu hình đúng cho Delta DVP:")
            print(f'  "port": "{port}", "baudrate": {baud}, "parity": "{parity}", "slave_id": {slave}')
            return
        print("không đọc được")
    print("\n✗ Không kết nối được Delta DVP.")
    print("Mặc định Delta DVP: 9600, Even, 1 stopbit. Kiểm tra trong WPL Soft/DIADesigner.")


def test_tcp(ip, port=502):
    """Test Modbus TCP (dùng cho PLC có cổng Ethernet hoặc qua gateway Modbus TCP)."""
    print(f"\n=== TEST MODBUS TCP: {ip}:{port} ===")
    try:
        from pymodbus.client import ModbusTcpClient
        client = ModbusTcpClient(ip, port=int(port), timeout=3)
        if not client.connect():
            print(f"✗ Không kết nối được {ip}:{port}")
            return
        result = client.read_holding_registers(0, count=4, slave=1)
        client.close()
        if result.isError():
            print(f"✗ Kết nối OK nhưng đọc lỗi: {result}")
        else:
            print(f"✓ Kết nối thành công! Thanh ghi 0-3: {list(result.registers)}")
    except Exception as e:
        print(f"✗ Lỗi: {e}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        list_ports()
    elif args[0] == "scan-modbus" and len(args) >= 2:
        scan_modbus(args[1])
    elif args[0] == "test-ls" and len(args) >= 2:
        test_ls(args[1])
    elif args[0] == "test-delta" and len(args) >= 2:
        test_delta(args[1])
    elif args[0] == "test-tcp" and len(args) >= 2:
        test_tcp(args[1], args[2] if len(args) > 2 else 502)
    else:
        print(__doc__)
