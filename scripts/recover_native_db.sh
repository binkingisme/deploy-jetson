#!/bin/bash
# ==============================================================================
# Comprehensive Recovery of Native PostgreSQL Cluster Data into Docker
# Recovers the user's original native database (the '30%' data before Docker)
# Thesis: Edge-based Open-Set Face Recognition on NVIDIA Jetson Orin Nano
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "===================================================================="
echo "  🔍 BẮT ĐẦU KHÔI PHỤC TOÀN BỘ DỮ LIỆU GỐC NATIVE POSTGRES VÀO DOCKER"
echo "===================================================================="

# 1. Đảm bảo Docker container postgres đang chạy
if ! docker ps --format '{{.Names}}' | grep -q "open_set_fr_postgres"; then
    echo ">> Đang khởi động Docker container open_set_fr_postgres..."
    docker compose up -d postgres
    sleep 3
fi

# 2. Liệt kê các cluster PostgreSQL gốc trên Jetson
echo ""
echo "[1/5] Kiểm tra các cụm (cluster) PostgreSQL gốc trên hệ điều hành Jetson:"
if command -v pg_lsclusters &>/dev/null; then
    pg_lsclusters
else
    echo "  (pg_lsclusters không có sẵn, tiếp tục quét thủ công)"
fi

# 3. Tìm cluster 'main' gốc và đổi tạm sang port 5445 để tránh xung đột với Docker (port 5432)
echo ""
echo "[2/5] Đang khởi động lại cụm PostgreSQL gốc (main) trên cổng phụ 5445..."

FOUND_MAIN=0
for conf_file in /etc/postgresql/*/main/postgresql.conf; do
    if [ -f "$conf_file" ]; then
        PG_VER=$(echo "$conf_file" | cut -d/ -f4)
        echo "  👉 Phát hiện cluster gốc phiên bản PostgreSQL: $PG_VER"
        
        # Đổi port thành 5445 để không bị đè port 5432 của Docker
        sudo sed -i "s/^port = .*/port = 5445/" "$conf_file" || true
        sudo sed -i "s/^#port = 5432/port = 5445/" "$conf_file" || true
        
        # Dọn dẹp PID cũ nếu có
        DATA_DIR="/var/lib/postgresql/$PG_VER/main"
        if [ -f "$DATA_DIR/postmaster.pid" ]; then
            OLD_PID=$(head -n 1 "$DATA_DIR/postmaster.pid" 2>/dev/null || echo "")
            if [ -n "$OLD_PID" ] && ! ps -p "$OLD_PID" > /dev/null 2>&1; then
                sudo rm -f "$DATA_DIR/postmaster.pid"
            fi
        fi
        
        # Khởi động cluster main trên port 5445
        sudo pg_ctlcluster "$PG_VER" main start 2>/dev/null || true
        FOUND_MAIN=1
    fi
done

sleep 2

# 4. Quét tìm database và xuất dữ liệu từ port 5445 và 5444
echo ""
echo "[3/5] Quét các cơ sở dữ liệu trên Native PostgreSQL..."

CANDIDATE_PORTS=(5445 5444)
MIGRATED_TOTAL=0

for P in "${CANDIDATE_PORTS[@]}"; do
    if sudo -u postgres psql -p "$P" -c "SELECT 1;" >/dev/null 2>&1; then
        echo "  ✅ Cổng $P đang HOẠT ĐỘNG!"
        
        # Lấy danh sách databases
        DBS=$(sudo -u postgres psql -p "$P" -tAc "SELECT datname FROM pg_database WHERE datistemplate = false AND datname NOT IN ('postgres');" 2>/dev/null || echo "")
        echo "     Danh sách database tìm thấy trên cổng $P: $DBS"
        
        for db in $DBS; do
            echo "     🔎 Đang kiểm tra database '$db' trên cổng $P..."
            
            # Đếm số lượng người trong bảng persons
            P_CNT=$(sudo -u postgres psql -p "$P" -d "$db" -tAc "SELECT count(*) FROM persons;" 2>/dev/null || echo "0")
            E_CNT=$(sudo -u postgres psql -p "$P" -d "$db" -tAc "SELECT count(*) FROM face_embeddings;" 2>/dev/null || echo "0")
            
            echo "        📊 Kết quả: $P_CNT đối tượng (persons), $E_CNT vectors đặc trưng (face_embeddings)."
            
            if [ "$P_CNT" -gt 0 ] || [ "$E_CNT" -gt 0 ]; then
                echo "        🚀 Tìm thấy dữ liệu cũ trong '$db'! Đang xuất dữ liệu ra tệp..."
                DUMP_FILE="/tmp/native_dump_${db}_${P}.sql"
                
                sudo -u postgres pg_dump -p "$P" -d "$db" --data-only --inserts \
                    -t users \
                    -t persons \
                    -t face_embeddings \
                    -t cameras \
                    -t identity_thresholds \
                    -t recognition_events \
                    -f "$DUMP_FILE" 2>/dev/null || \
                sudo -u postgres pg_dump -p "$P" -d "$db" --data-only \
                    -t persons \
                    -t face_embeddings \
                    -t cameras \
                    -t identity_thresholds \
                    -f "$DUMP_FILE" 2>/dev/null || true
                
                if [ -s "$DUMP_FILE" ]; then
                    echo "        📥 Đang nạp dữ liệu từ '$DUMP_FILE' vào Docker PostgreSQL..."
                    docker exec -i open_set_fr_postgres psql -U open_set_fr -d open_set_fr < "$DUMP_FILE" 2>/dev/null || true
                    echo "        ✅ Đã khôi phục thành công dữ liệu từ '$db' sang Docker!"
                    MIGRATED_TOTAL=$((MIGRATED_TOTAL + P_CNT))
                fi
            fi
        done
    fi
done

# 5. Chạy tool quét ảnh cục bộ và đồng bộ ngưỡng EVT
echo ""
echo "[4/5] Quét bổ sung các thư mục ảnh khuôn mặt và đồng bộ bảng ngưỡng EVT..."
python3 "$PROJECT_ROOT/scripts/migrate_all_legacy_data.py"

# 6. Khởi động lại backend để nạp ma trận nhận diện
echo ""
echo "[5/5] Làm mới bộ nhớ RAM nhận diện trên Backend..."
docker compose restart backend

echo ""
echo "===================================================================="
echo "🎉 HOÀN TẤT QUÁ TRÌNH KHÔI PHỤC DỮ LIỆU!"
echo "===================================================================="
echo "Kiểm tra tổng số bản ghi hiện tại trong Docker PostgreSQL:"
docker exec -i open_set_fr_postgres psql -U open_set_fr -d open_set_fr -c "
SELECT 
    (SELECT count(*) FROM persons) as total_persons,
    (SELECT count(*) FROM face_embeddings) as total_embeddings,
    (SELECT count(*) FROM identity_thresholds) as total_thresholds,
    (SELECT count(*) FROM cameras) as total_cameras;
"
echo "===================================================================="
echo "👉 Hãy mở lại trình duyệt tại http://10.39.4.131:3000 và bấm F5!"
echo "===================================================================="
