#!/bin/bash
# ==============================================================================
# Comprehensive Fix & Startup for Native PostgreSQL Cluster 14 on Port 5445
# Thesis: Edge-based Open-Set Face Recognition on NVIDIA Jetson Orin Nano
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "===================================================================="
echo "  🚀 KHẮC PHỤC TRIỆT ĐỂ & BẬT LẠI CỤM NATIVE POSTGRESQL 14 (PORT 5445)"
echo "===================================================================="

# 1. Tắt tận gốc tiến trình postgres 14 native bị treo ngầm
echo ">> [1/5] Dừng các tiến trình PostgreSQL 14 cũ bị treo..."
sudo pkill -9 -f "/usr/lib/postgresql/14/bin/postgres" 2>/dev/null || true
sleep 1

# 2. Xóa các khối Shared Memory (IPC) và Semaphores bị chiếm giữ
echo ">> [2/5] Giải phóng Shared Memory (IPC) bị giữ bởi tiến trình cũ..."
for id in $(ipcs -m 2>/dev/null | awk '$3=="postgres" {print $2}'); do
    sudo ipcrm -m "$id" 2>/dev/null || true
done
for id in $(ipcs -s 2>/dev/null | awk '$3=="postgres" {print $2}'); do
    sudo ipcrm -s "$id" 2>/dev/null || true
done

# 3. Dọn dẹp file PID lock và Socket lock
echo ">> [3/5] Dọn dẹp file lock PID và socket..."
DATA_DIR="/var/lib/postgresql/14/main"
sudo rm -f "$DATA_DIR/postmaster.pid" 2>/dev/null || true
sudo rm -f /var/run/postgresql/.s.PGSQL.5445* 2>/dev/null || true
sudo rm -f /tmp/.s.PGSQL.5445* 2>/dev/null || true

sudo mkdir -p /var/run/postgresql
sudo chown -R postgres:postgres /var/run/postgresql
sudo chmod 2775 /var/run/postgresql

# 4. Cấu hình port 5445 và xác thực trust cho localhost trong pg_hba.conf
echo ">> [4/5] Cấu hình port 5445 và quyền truy cập localhost..."
CONF_FILE="/etc/postgresql/14/main/postgresql.conf"
if [ -f "$CONF_FILE" ]; then
    sudo sed -i "s/^port = .*/port = 5445/" "$CONF_FILE" || true
    sudo sed -i "s/^#port = 5432/port = 5445/" "$CONF_FILE" || true
    sudo sed -i "s/^#listen_addresses = .*/listen_addresses = '*'/" "$CONF_FILE" || true
fi

HBA_FILE="/etc/postgresql/14/main/pg_hba.conf"
if [ -f "$HBA_FILE" ]; then
    # Chuyển localhost sang trust để Python và psql kết nối tự do mà không bị lỗi password
    sudo sed -i 's/127\.0\.0\.1\/32.*scram-sha-256/127.0.0.1\/32            trust/' "$HBA_FILE" || true
    sudo sed -i 's/127\.0\.0\.1\/32.*md5/127.0.0.1\/32            trust/' "$HBA_FILE" || true
fi

# 5. Khởi động cụm PostgreSQL 14
echo ">> [5/5] Đang khởi động cụm 14 main..."
sudo pg_ctlcluster 14 main start

sleep 2

# Kiểm tra trạng thái
echo ""
echo "📊 Trạng thái các cụm PostgreSQL:"
pg_lsclusters

echo ""
if sudo -u postgres psql -p 5445 -c "SELECT 1;" >/dev/null 2>&1; then
    echo "===================================================================="
    echo "  🎉 CỤM 14 MAIN ĐÃ HOẠT ĐỘNG ONLINE TRÊN CỔNG 5445!"
    echo "===================================================================="
    echo ">> Danh sách database tìm thấy:"
    sudo -u postgres psql -p 5445 -c "\l"
    echo ""
    echo ">> Tự động chạy đối chiếu Database ngay bây giờ:"
    echo "--------------------------------------------------------------------"
    python3 "$PROJECT_ROOT/scripts/compare_dbs.py"
else
    echo "===================================================================="
    echo "⚠️ Cụm chưa bật được. Xem log mới nhất tại:"
    sudo tail -n 25 /var/log/postgresql/postgresql-14-main.log
    echo "===================================================================="
fi
