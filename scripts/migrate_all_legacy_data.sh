#!/bin/bash
# ==============================================================================
# One-Click Legacy Data & Face Gallery Migration to Docker
# Thesis: Edge-based Open-Set Face Recognition on NVIDIA Jetson Orin Nano
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "===================================================================="
echo "  🚀 CHUYỂN TOÀN BỘ DỮ LIỆU CŨ SANG DOCKER (Spec v3 §12, §18, §25)"
echo "===================================================================="

# 1. Đảm bảo các Docker container đang chạy
if ! docker ps --format '{{.Names}}' | grep -q "open_set_fr_postgres"; then
    echo ">> Khởi động Docker container open_set_fr_postgres..."
    docker start open_set_fr_postgres || docker compose up -d postgres
    sleep 3
fi

if ! docker ps --format '{{.Names}}' | grep -q "open_set_fr_backend"; then
    echo ">> Khởi động Docker container open_set_fr_backend..."
    docker start open_set_fr_backend || docker compose up -d backend
    sleep 3
fi

# 2. Đảm bảo quyền ghi vào thư mục static/enrolled_faces
mkdir -p "$PROJECT_ROOT/backend/static/enrolled_faces"
chmod -R 777 "$PROJECT_ROOT/backend/static/enrolled_faces" 2>/dev/null || true

# 3. Cài đặt các thư viện cần thiết nếu chạy trực tiếp trên Jetson Host
if ! python3 -c "import psycopg2, numpy" 2>/dev/null; then
    echo ">> Đang cài đặt thư viện hỗ trợ (psycopg2-binary, numpy)..."
    pip3 install psycopg2-binary numpy --quiet 2>/dev/null || pip install psycopg2-binary numpy --quiet 2>/dev/null || true
fi

# 4. Chạy script migration toàn diện
echo ""
python3 "$PROJECT_ROOT/scripts/migrate_all_legacy_data.py"

# 5. Khởi động lại backend để chắc chắn RAM nạp lại 100% Gallery
echo ""
echo ">> Làm mới bộ nhớ đệm ma trận nhận diện trên Backend..."
docker compose restart backend

echo ""
echo "===================================================================="
echo "🎉 HOÀN TẤT CHUYỂN ĐỔI TOÀN BỘ DỮ LIỆU CŨ!"
echo "===================================================================="
echo "Hãy quay lại trình duyệt và nhấn F5 (hoặc nút 'Reload Gallery')!"
echo "===================================================================="
