#!/bin/bash
# ==============================================================================
# Comprehensive Jetson PostgreSQL Database Auto-Fix & Repair Tool
# Thesis: Edge-based Open-Set Face Recognition
# ==============================================================================
set -e

echo "===================================================================="
echo "  🛠️  BẮT ĐẦU KIỂM TRA VÀ TỰ ĐỘNG KHẮC PHỤC LỖI DATABASE JETSON"
echo "===================================================================="

# 1. Kiểm tra / khởi động service PostgreSQL
echo "[1/6] Kiểm tra dịch vụ PostgreSQL trên hệ điều hành..."
if ! command -v psql &> /dev/null; then
    echo "[!] PostgreSQL chưa được cài đặt. Đang tiến hành cài đặt..."
    sudo apt-get update -y
    sudo apt-get install -y postgresql postgresql-contrib
fi

echo "[2/6] Kích hoạt và khởi động lại PostgreSQL service..."
sudo systemctl enable postgresql || true
sudo systemctl restart postgresql

if sudo systemctl is-active --quiet postgresql; then
    echo "  ✅ Dịch vụ PostgreSQL đang CHẠY (active)."
else
    echo "  ❌ Không thể khởi động PostgreSQL service!"
    sudo systemctl status postgresql --no-pager
    exit 1
fi

# 2. Tạo role và database open_set_fr
echo "[3/6] Thiết lập tài khoản và cơ sở dữ liệu 'open_set_fr'..."
sudo -u postgres psql -c "DO \$\$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'open_set_fr') THEN
        CREATE ROLE open_set_fr WITH LOGIN PASSWORD 'open_set_fr_pass';
    ELSE
        ALTER ROLE open_set_fr WITH LOGIN PASSWORD 'open_set_fr_pass';
    END IF;
END \$\$;"

sudo -u postgres psql -c "SELECT 'CREATE DATABASE open_set_fr OWNER open_set_fr' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'open_set_fr')\gexec"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE open_set_fr TO open_set_fr;"
sudo -u postgres psql -d open_set_fr -c "GRANT ALL ON SCHEMA public TO open_set_fr;" || true
sudo -u postgres psql -d open_set_fr -c "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";" || true

# 3. Cấu hình pg_hba.conf và postgresql.conf để kết nối nội bộ 127.0.0.1 không bị chặn
echo "[4/6] Cấu hình quyền kết nối mạng nội bộ (pg_hba.conf)..."
PG_VER=$(psql -V 2>/dev/null | awk '{print $3}' | cut -d. -f1 || echo "14")
CONF_DIR="/etc/postgresql/$PG_VER/main"
if [ -d "$CONF_DIR" ]; then
    sudo sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" "$CONF_DIR/postgresql.conf" || true
    sudo sed -i "s/listen_addresses = 'localhost'/listen_addresses = '*'/" "$CONF_DIR/postgresql.conf" || true

    if ! sudo grep -q "open_set_fr" "$CONF_DIR/pg_hba.conf"; then
        echo "host    open_set_fr     open_set_fr     127.0.0.1/32            md5" | sudo tee -a "$CONF_DIR/pg_hba.conf" > /dev/null
        echo "host    open_set_fr     open_set_fr     ::1/128                 md5" | sudo tee -a "$CONF_DIR/pg_hba.conf" > /dev/null
        sudo systemctl restart postgresql
    fi
fi

# 4. Áp dụng bảng dữ liệu từ init_schema.sql
echo "[5/6] Khởi tạo các bảng dữ liệu (schema)..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SQL_FILE="$(dirname "$SCRIPT_DIR")/database/init_schema.sql"
if [ -f "$SQL_FILE" ]; then
    PGPASSWORD="open_set_fr_pass" psql -h 127.0.0.1 -U open_set_fr -d open_set_fr -f "$SQL_FILE" || true
    # Migration Spec v3 §13.2
    PGPASSWORD="open_set_fr_pass" psql -h 127.0.0.1 -U open_set_fr -d open_set_fr -c "ALTER TABLE persons ADD COLUMN IF NOT EXISTS created_by UUID REFERENCES users(user_id);" || true
fi

# 5. Kiểm tra kết nối thực tế
echo "[6/6] Kiểm tra kết nối từ Python/PostgreSQL..."
python3 -c "
import os, sys
sys.path.insert(0, '$(dirname "$SCRIPT_DIR")/backend')
try:
    import psycopg2
    conn = psycopg2.connect('postgresql://open_set_fr:open_set_fr_pass@127.0.0.1:5432/open_set_fr', connect_timeout=3)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = \'public\';')
    count = cur.fetchone()[0]
    conn.close()
    print(f'  ✅ Kết nối thành công! Tìm thấy {count} bảng trong database open_set_fr.')
except Exception as e:
    print(f'  ❌ Lỗi kết nối Python: {e}')
    sys.exit(1)
"

echo "===================================================================="
echo "🎉 HOÀN TẤT KHẮC PHỤC LỖI DATABASE TRÊN JETSON!"
echo "Database URL: postgresql://open_set_fr:open_set_fr_pass@127.0.0.1:5432/open_set_fr"
echo "===================================================================="
