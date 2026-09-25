#!/bin/bash
# ==============================================================================
# Diagnose & Fix Native PostgreSQL 14 Startup Failure
# Thesis: Edge-based Open-Set Face Recognition on NVIDIA Jetson Orin Nano
# ==============================================================================
set -e

echo "===================================================================="
echo "  🔍 CHẨN ĐOÁN & TỰ ĐỘNG SỬA LỖI NATIVE POSTGRESQL 14"
echo "===================================================================="

LOG_FILE="/var/log/postgresql/postgresql-14-main.log"
DATA_DIR="/var/lib/postgresql/14/main"
CONF_FILE="/etc/postgresql/14/main/postgresql.conf"

# 1. Đọc ngay 20 dòng log lỗi cuối cùng
echo ""
echo "📄 [1/5] 20 DÒNG LOG LỖI MỚI NHẤT TỪ $LOG_FILE:"
echo "--------------------------------------------------------------------"
if [ -f "$LOG_FILE" ]; then
    sudo tail -n 20 "$LOG_FILE"
else
    echo "  (Chưa có file log hoặc file rỗng)"
fi
echo "--------------------------------------------------------------------"

# 2. Dọn dẹp triệt để các file khóa (locks)
echo ""
echo "🧹 [2/5] Dọn dẹp các file lock PID và Socket..."
sudo rm -f "$DATA_DIR/postmaster.pid" 2>/dev/null || true
sudo rm -f /var/run/postgresql/.s.PGSQL.* 2>/dev/null || true
sudo rm -f /tmp/.s.PGSQL.* 2>/dev/null || true

# 3. Sửa phân quyền thư mục dữ liệu và socket
echo "🔑 [3/5] Đặt lại quyền chuẩn cho thư mục dữ liệu (postgres:postgres 0700)..."
sudo chown -R postgres:postgres "$DATA_DIR"
sudo chmod 700 "$DATA_DIR"
sudo mkdir -p /var/run/postgresql
sudo chown -R postgres:postgres /var/run/postgresql
sudo chmod 2775 /var/run/postgresql

# 4. Kiểm tra cấu hình ssl và listen_addresses trong postgresql.conf
echo "⚙️  [4/5] Tối ưu cấu hình trong $CONF_FILE..."
if [ -f "$CONF_FILE" ]; then
    # Đảm bảo port là 5445
    sudo sed -i "s/^port = .*/port = 5445/" "$CONF_FILE"
    # Đảm bảo listen_addresses bật
    sudo sed -i "s/^#listen_addresses = .*/listen_addresses = '*'/" "$CONF_FILE"
    # Nếu ssl lỗi, tạm thời tắt ssl để tránh lỗi chứng chỉ snakeoil
    if grep -q "could not load private key file" "$LOG_FILE" 2>/dev/null; then
        echo "  👉 Phát hiện lỗi SSL key! Đang tạm tắt ssl..."
        sudo sed -i "s/^ssl = on/ssl = off/" "$CONF_FILE"
    fi
fi

# 5. Thử chạy trực tiếp binary postgres bằng user postgres để kiểm tra
echo ""
echo "🚀 [5/5] Thử khởi động lại cụm bằng pg_ctlcluster..."
sudo pg_ctlcluster 14 main start || true

echo ""
echo "📊 Trạng thái cụm hiện tại:"
pg_lsclusters

echo ""
if sudo -u postgres psql -p 5445 -c "SELECT 1;" >/dev/null 2>&1; then
    echo "===================================================================="
    echo "  🎉 THÀNH CÔNG: Cụm PostgreSQL 14 đã ONLINE trên cổng 5445!"
    echo "===================================================================="
    echo "Tiếp tục chạy đối chiếu: bash scripts/compare_dbs.sh"
else
    echo "===================================================================="
    echo "  ⚠️ Cụm vẫn chưa lên. Thử chạy trực tiếp lệnh kiểm tra sau:"
    echo "  sudo -u postgres /usr/lib/postgresql/14/bin/postgres -D $DATA_DIR -c config_file=$CONF_FILE"
    echo "===================================================================="
fi
