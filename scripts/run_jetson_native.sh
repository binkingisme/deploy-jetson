#!/bin/bash
# ==============================================================================
# Native All-in-One Runner on NVIDIA Jetson Orin Nano
# Serves React Dashboard + FastAPI Backend + WebSockets on Port 8000
# Zero Docker dependency, Zero kernel veth/bridge issues!
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "===================================================================="
echo "  🚀 KHỞI CHẠY HỆ THỐNG JETSON OPEN-SET FACE RECOGNITION (NATIVE)"
echo "===================================================================="

# 1. Đảm bảo PostgreSQL đang chạy
echo "[1/3] Kiểm tra dịch vụ Database PostgreSQL..."
if command -v systemctl &> /dev/null; then
    sudo systemctl start postgresql 2>/dev/null || true
    if systemctl is-active --quiet postgresql; then
        echo "  ✅ PostgreSQL service: ACTIVE"
    else
        echo "  ⚠️ PostgreSQL chưa chạy, đang chạy script fix database..."
        bash scripts/fix_jetson_db.sh || true
    fi
fi

# 2. Cài đặt dependency backend nếu thiếu
echo "[2/3] Kiểm tra thư viện Python Backend..."
cd "$PROJECT_ROOT/backend"
if [ -f requirements.txt ]; then
    pip3 install -r requirements.txt --quiet 2>/dev/null || pip install -r requirements.txt --quiet || true
fi

# 3. Lấy địa chỉ IP Jetson
IP_ADDR=$(hostname -I | awk '{print $1}' || echo "localhost")

echo "===================================================================="
echo "🎉 HỆ THỐNG ĐANG BẮT ĐẦU CHẠY TRÊN CỔNG 8000!"
echo "===================================================================="
echo "  🖥️  Web Dashboard:     http://${IP_ADDR}:8000   (hoặc http://localhost:8000)"
echo "  ⚙️  FastAPI Swagger:    http://${IP_ADDR}:8000/docs"
echo "  🔌  WebSocket Live:     ws://${IP_ADDR}:8000/ws/inference"
echo "  🗄️  PostgreSQL DB:      localhost:5432 (Database: open_set_fr)"
echo "===================================================================="
echo "👉 Mở trình duyệt trên máy tính/laptop cùng mạng LAN và truy cập:"
echo "   http://${IP_ADDR}:8000"
echo "===================================================================="

export DATABASE_URL="postgresql://open_set_fr:open_set_fr_pass@localhost:5432/open_set_fr"
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
