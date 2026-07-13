#!/bin/bash
# ================================================================
# Script cài đặt SCADA Gateway tự động
# Chạy: bash install_gateway.sh
# ================================================================

set -e
GATEWAY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="scada-gateway"
PYTHON_BIN="python3"

echo ""
echo "╔════════════════════════════════════════╗"
echo "║     SCADA Gateway - Cài đặt tự động    ║"
echo "╚════════════════════════════════════════╝"
echo ""

# --- Kiểm tra Python ---
if ! command -v $PYTHON_BIN &>/dev/null; then
    echo "❌ Python3 chưa được cài. Chạy: sudo apt install python3 python3-pip"
    exit 1
fi
PYTHON_VERSION=$($PYTHON_BIN --version | cut -d' ' -f2)
echo "✓ Python $PYTHON_VERSION"

# --- Cài thư viện ---
echo ""
echo "→ Cài thư viện Python..."
pip3 install -r "$GATEWAY_DIR/requirements.txt" --break-system-packages --quiet 2>/dev/null \
    || pip3 install -r "$GATEWAY_DIR/requirements.txt" --quiet

echo "✓ Thư viện đã cài xong"

# --- Kiểm tra file config ---
CONFIG_FILE="$GATEWAY_DIR/config.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo ""
    echo "⚠️  Chưa có file config.json!"
    echo "   Tải file cấu hình từ trang quản trị:"
    echo "   Admin → Thiết bị & Tag → Tải file cấu hình gateway"
    echo "   Đặt file đó vào: $CONFIG_FILE"
    echo "   Rồi chạy lại script này."
    echo ""
    echo "   Hoặc copy từ ví dụ:"
    echo "   cp $GATEWAY_DIR/config.example.json $CONFIG_FILE"
    exit 1
fi

# --- Kiểm tra config.json hợp lệ ---
if ! $PYTHON_BIN -c "import json; json.load(open('$CONFIG_FILE'))" 2>/dev/null; then
    echo "❌ config.json không hợp lệ (lỗi JSON). Kiểm tra lại file."
    exit 1
fi

SITE_KEY=$($PYTHON_BIN -c "import json; print(json.load(open('$CONFIG_FILE'))['site_key'])")
echo "✓ Site key: $SITE_KEY"

# --- Test kết nối MQTT ---
echo ""
echo "→ Test kết nối MQTT..."
$PYTHON_BIN - << PYEOF
import json, sys
try:
    import paho.mqtt.client as mqtt
    cfg = json.load(open("$CONFIG_FILE"))["mqtt"]
    client = mqtt.Client(client_id="test_install")
    client.username_pw_set(cfg["username"], cfg["password"])
    results = {}
    def on_connect(c, u, f, rc):
        results["rc"] = rc
        c.disconnect()
    client.on_connect = on_connect
    client.connect(cfg["host"], cfg.get("port", 1883), keepalive=5)
    client.loop_start()
    import time; time.sleep(3)
    client.loop_stop()
    if results.get("rc") == 0:
        print("✓ MQTT kết nối OK")
    elif results.get("rc") == 5:
        print("❌ MQTT lỗi xác thực (sai username/password) - kiểm tra config.json")
        sys.exit(1)
    else:
        print(f"❌ MQTT lỗi rc={results.get('rc')} - kiểm tra host/port")
        sys.exit(1)
except Exception as e:
    print(f"❌ Không test được MQTT: {e}")
    sys.exit(1)
PYEOF

# --- Chạy thử ---
echo ""
echo "→ Chạy thử gateway 5 giây..."
timeout 5 $PYTHON_BIN "$GATEWAY_DIR/universal_gateway.py" "$CONFIG_FILE" || true
echo ""

# --- Cài systemd service (Linux) ---
if command -v systemctl &>/dev/null && [ "$EUID" -eq 0 ]; then
    echo "→ Cài systemd service tự động chạy khi khởi động..."
    cat > /etc/systemd/system/$SERVICE_NAME.service << SERVICE
[Unit]
Description=SCADA Gateway ($SITE_KEY)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(logname 2>/dev/null || echo root)
WorkingDirectory=$GATEWAY_DIR
ExecStart=$PYTHON_BIN $GATEWAY_DIR/universal_gateway.py $CONFIG_FILE
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SERVICE

    systemctl daemon-reload
    systemctl enable $SERVICE_NAME
    systemctl start $SERVICE_NAME
    echo ""
    echo "✅ Đã cài service: $SERVICE_NAME"
    echo ""
    echo "Lệnh quản lý:"
    echo "  systemctl status $SERVICE_NAME   # xem trạng thái"
    echo "  journalctl -u $SERVICE_NAME -f   # xem log realtime"
    echo "  systemctl restart $SERVICE_NAME  # khởi động lại"
    echo "  systemctl stop $SERVICE_NAME     # dừng"

elif command -v pm2 &>/dev/null; then
    echo "→ Cài PM2 process manager..."
    pm2 start "$PYTHON_BIN" --name "$SERVICE_NAME" --interpreter none \
        -- "$GATEWAY_DIR/universal_gateway.py" "$CONFIG_FILE"
    pm2 save
    echo "✅ Đã cài PM2: $SERVICE_NAME"
    echo "  pm2 logs $SERVICE_NAME   # xem log"
    echo "  pm2 restart $SERVICE_NAME"

else
    echo ""
    echo "═══════════════════════════════════════"
    echo "✅ Cài đặt hoàn tất!"
    echo ""
    echo "Chạy gateway thủ công:"
    echo "  cd $GATEWAY_DIR"
    echo "  python3 universal_gateway.py config.json"
    echo ""
    echo "Để tự chạy khi khởi động (không có root/systemd):"
    echo "  pip3 install pm2  hoặc  pip3 install supervisor"
    echo ""
fi

echo "═══════════════════════════════════════"
echo "Công cụ chẩn đoán nếu gặp lỗi kết nối PLC:"
echo "  python3 $GATEWAY_DIR/diagnose.py              # liệt kê cổng COM"
echo "  python3 $GATEWAY_DIR/diagnose.py test-ls COM8 # test PLC LS XGB"
echo "  python3 $GATEWAY_DIR/diagnose.py scan-modbus COM8 # quét tự động"
echo "═══════════════════════════════════════"
