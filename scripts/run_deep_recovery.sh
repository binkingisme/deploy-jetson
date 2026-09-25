#!/bin/bash
# ==============================================================================
# One-Click Deep Recovery of 30-40+ Identities on Jetson Orin Nano
# Recovers from:
# 1. Jetson threshold_table.json & /tmp/threshold_table_jetson.json
# 2. DeepStream known_embeddings.npz & .faiss
# 3. Native PostgreSQL cluster main (port 5445)
# 4. Face image directories (data/, dataset/, capture/, static/)
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "===================================================================="
echo "  🚀 KHÔI PHỤC TOÀN DIỆN 30-40+ DANH TÍNH CŨ VÀO DOCKER"
echo "===================================================================="

# 1. Đảm bảo container Docker đang chạy
if ! docker ps --format '{{.Names}}' | grep -q "open_set_fr_postgres"; then
    echo ">> Khởi động Docker container postgres..."
    docker compose up -d postgres
    sleep 3
fi

# 2. Kiểm tra và kích hoạt cluster PostgreSQL main gốc (port 5445) nếu có
for conf in /etc/postgresql/*/main/postgresql.conf; do
    if [ -f "$conf" ]; then
        PG_VER=$(echo "$conf" | cut -d/ -f4)
        sudo sed -i "s/^port = .*/port = 5445/" "$conf" 2>/dev/null || true
        sudo sed -i "s/^#port = 5432/port = 5445/" "$conf" 2>/dev/null || true
        sudo pg_ctlcluster "$PG_VER" main start 2>/dev/null || true
    fi
done

# 3. Chạy script khôi phục toàn diện
python3 "$PROJECT_ROOT/scripts/deep_recovery_jetson.py"

# 4. Khởi động lại backend để nạp ma trận nhận diện
docker compose restart backend

echo ""
echo "===================================================================="
echo "🎉 HOÀN TẤT! Hãy mở trình duyệt tại http://10.39.4.131:3000 và bấm F5!"
echo "===================================================================="
