#!/bin/bash
# ==============================================================================
# Migrate data from Native PostgreSQL (Port 5444) to Docker Container (Port 5432)
# Open-Set Face Recognition Thesis Project
# ==============================================================================
set -e

cd /tmp

echo "===================================================================="
echo "  📦 CHUYỂN DỮ LIỆU TỪ NATIVE POSTGRES (PORT 5444) SANG DOCKER"
echo "===================================================================="

# Đảm bảo Docker postgres container đang chạy
if ! docker ps --format '{{.Names}}' | grep -q "open_set_fr_postgres"; then
    echo ">> Khởi động Docker container open_set_fr_postgres..."
    docker start open_set_fr_postgres
    sleep 3
fi

PORT=5444
# Kiểm tra xem port 5444 có đang hoạt động không
if ! sudo -u postgres psql -p 5444 -c "SELECT 1;" >/dev/null 2>&1; then
    echo "  >> Thử kết nối port 5432..."
    if sudo -u postgres psql -p 5432 -c "SELECT 1;" >/dev/null 2>&1; then
        PORT=5432
    fi
fi

echo "  ✅ Đã phát hiện Native PostgreSQL đang chạy trên PORT: $PORT"

# Kiểm tra dữ liệu trong database Native
echo ">> Kiểm tra số lượng người trong database Native cũ..."
COUNT_PERSONS=$(sudo -u postgres psql -p $PORT -d open_set_fr -tAc "SELECT count(*) FROM persons;" 2>/dev/null || echo "0")
COUNT_EMB=$(sudo -u postgres psql -p $PORT -d open_set_fr -tAc "SELECT count(*) FROM face_embeddings;" 2>/dev/null || echo "0")
echo "  📊 Dữ liệu Native cũ: $COUNT_PERSONS người, $COUNT_EMB vectors đặc trưng."

DUMP_FILE="/tmp/legacy_open_set_fr_data.sql"
rm -f "$DUMP_FILE"

echo ">> Đang xuất dữ liệu từ Native PostgreSQL (port $PORT)..."
sudo -u postgres pg_dump -p $PORT -d open_set_fr --data-only \
    -t persons \
    -t face_embeddings \
    -t cameras \
    -t recognition_events \
    -t identity_thresholds \
    --inserts \
    --on-conflict-do-nothing \
    -f "$DUMP_FILE" 2>/dev/null || \
sudo -u postgres pg_dump -p $PORT -d open_set_fr --data-only \
    -t persons \
    -t face_embeddings \
    -t cameras \
    -t recognition_events \
    -t identity_thresholds \
    -f "$DUMP_FILE"

echo "  ✅ Xuất dữ liệu thành công ra $DUMP_FILE"

echo ">> Đang nạp dữ liệu vào Docker PostgreSQL container..."
docker exec -i open_set_fr_postgres psql -U open_set_fr -d open_set_fr < "$DUMP_FILE"

echo ">> Khởi động lại Backend để nạp lại ma trận Gallery..."
docker compose restart backend

echo ""
echo "===================================================================="
echo "🎉 HOÀN TẤT CHUYỂN TOÀN BỘ DỮ LIỆU SANG DOCKER!"
echo "===================================================================="
docker exec -i open_set_fr_postgres psql -U open_set_fr -d open_set_fr -c "
SELECT 
    (SELECT count(*) FROM persons) as total_persons,
    (SELECT count(*) FROM face_embeddings) as total_embeddings,
    (SELECT count(*) FROM cameras) as total_cameras,
    (SELECT count(*) FROM identity_thresholds) as total_thresholds;
"
echo "===================================================================="
echo "Hãy quay lại trình duyệt và nhấn nút 'Reload Gallery' (hoặc F5)!"
echo "===================================================================="
