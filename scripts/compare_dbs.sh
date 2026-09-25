#!/bin/bash
# ==============================================================================
# One-Click Database Reconciliation: Native PostgreSQL vs Docker PostgreSQL
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "===================================================================="
echo "  🔍 CÔNG CỤ ĐỐI CHIẾU DATABASE GỐC (NATIVE) VÀ DATABASE MỚI (DOCKER)"
echo "===================================================================="

# 1. Đảm bảo Docker DB đang chạy
if ! docker ps --format '{{.Names}}' | grep -q "open_set_fr_postgres"; then
    echo ">> Đang khởi động Docker PostgreSQL container..."
    docker compose up -d postgres
    sleep 2
fi

# 2. Kiểm tra xem Native Postgres có đang chạy ở port 5445/5444 không
RUNNING_OLD=0
for P in 5445 5444 5433; do
    if sudo -u postgres psql -p "$P" -c "SELECT 1;" >/dev/null 2>&1; then
        RUNNING_OLD=1
        break
    fi
done

# Nếu chưa chạy, bật cluster native main trên port 5445
if [ "$RUNNING_OLD" -eq 0 ]; then
    echo ">> Cụm Native PostgreSQL đang dừng. Đang dọn dẹp tiến trình cũ, IPC shared memory và khởi động cổng 5445..."
    sudo pkill -9 -f "/usr/lib/postgresql/14/bin/postgres" 2>/dev/null || true
    for id in $(ipcs -m 2>/dev/null | awk '$3=="postgres" {print $2}'); do
        sudo ipcrm -m "$id" 2>/dev/null || true
    done
    for id in $(ipcs -s 2>/dev/null | awk '$3=="postgres" {print $2}'); do
        sudo ipcrm -s "$id" 2>/dev/null || true
    done

    for pid_file in /var/lib/postgresql/*/main/postmaster.pid; do
        if [ -f "$pid_file" ]; then
            sudo rm -f "$pid_file"
        fi
    done
    sudo rm -f /var/run/postgresql/.s.PGSQL.5445* /tmp/.s.PGSQL.5445* 2>/dev/null || true
    sudo mkdir -p /var/run/postgresql
    sudo chown -R postgres:postgres /var/run/postgresql
    sudo chmod 2775 /var/run/postgresql

    for conf_file in /etc/postgresql/*/main/postgresql.conf; do
        if [ -f "$conf_file" ]; then
            PG_VER=$(echo "$conf_file" | cut -d/ -f4)
            sudo sed -i "s/^port = .*/port = 5445/" "$conf_file" || true
            sudo sed -i "s/^#port = 5432/port = 5445/" "$conf_file" || true
            sudo sed -i "s/^#listen_addresses = .*/listen_addresses = '*'/" "$conf_file" || true
            sudo sed -i "s/^listen_addresses = .*/listen_addresses = '*'/" "$conf_file" || true

            HBA_FILE="/etc/postgresql/$PG_VER/main/pg_hba.conf"
            if [ -f "$HBA_FILE" ]; then
                sudo sed -i 's/127\.0\.0\.1\/32.*scram-sha-256/127.0.0.1\/32            trust/' "$HBA_FILE" || true
                sudo sed -i 's/127\.0\.0\.1\/32.*md5/127.0.0.1\/32            trust/' "$HBA_FILE" || true
            fi

            sudo pg_ctlcluster "$PG_VER" main start || true
        fi
    done
    sleep 2
fi

# 3. Đảm bảo pg_hba.conf cho phép trust trên localhost để script Python kết nối được
for hba in /etc/postgresql/*/main/pg_hba.conf; do
    if [ -f "$hba" ]; then
        if ! grep -q "Antigravity Trust" "$hba"; then
            echo ">> Cấp quyền kết nối trust nội bộ trong $hba..."
            sudo sed -i '1s/^/# Antigravity Trust\nhost all all 127.0.0.1\/32 trust\nlocal all all trust\n/' "$hba" || true
            sudo pg_ctlcluster 14 main reload 2>/dev/null || true
        fi
    fi
done

# 4. Cài đặt psycopg2 nếu thiếu
if ! python3 -c "import psycopg2" 2>/dev/null; then
    pip3 install psycopg2-binary --quiet 2>/dev/null || true
fi

# 5. Chạy script đối chiếu
python3 "$PROJECT_ROOT/scripts/compare_dbs.py" "$@"
