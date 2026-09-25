#!/bin/bash
# ==============================================================================
# One-Click Restore of 37-Entry EVT Threshold Table & Enrolled Persons
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "===================================================================="
echo "  🎯 KHÔI PHỤC TOÀN BỘ 37 BẢN GHI NGƯỠNG EVT & DANH TÍNH"
echo "===================================================================="

# 1. Khôi phục file JSON gốc nếu đang nằm trong /tmp/threshold_table_jetson.json
if [ -f "/tmp/threshold_table_jetson.json" ]; then
    echo ">> Tìm thấy file gốc tại /tmp/threshold_table_jetson.json! Đang khôi phục..."
    mkdir -p "$PROJECT_ROOT/thresholds"
    cp /tmp/threshold_table_jetson.json "$PROJECT_ROOT/thresholds/threshold_table.json"
fi

# 2. Cài đặt thư viện hỗ trợ nếu thiếu
if ! python3 -c "import psycopg2, numpy" 2>/dev/null; then
    pip3 install psycopg2-binary numpy --quiet 2>/dev/null || true
fi

# 3. Chạy script khôi phục toàn bộ 37 entries
python3 "$PROJECT_ROOT/scripts/restore_37_thresholds.py"

# 4. Khởi động lại backend để nạp lại ma trận RAM
docker compose restart backend

echo ""
echo "===================================================================="
echo "🎉 HOÀN TẤT KHÔI PHỤC! Hãy mở lại trình duyệt và bấm F5!"
echo "===================================================================="
