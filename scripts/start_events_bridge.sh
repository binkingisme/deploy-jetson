#!/bin/bash
# ==============================================================================
# One-Click Live Realtime Event Sync Bridge
# Streams recognition events from Native Postgres (5444/5445) to Docker Postgres (5432)
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "===================================================================="
echo "  🚀 KHỞI ĐỘNG CẦU NỐI ĐỒNG BỘ SỰ KIỆN NHẬN DIỆN REAL-TIME (1s)"
echo "===================================================================="

# Cài thư viện nếu thiếu
if ! python3 -c "import psycopg2" 2>/dev/null; then
    pip3 install psycopg2-binary --quiet 2>/dev/null || true
fi

# Chạy bridge đồng bộ realtime
python3 "$PROJECT_ROOT/scripts/diagnose_and_sync_events.py" "$@"
