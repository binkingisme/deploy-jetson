#!/bin/bash
# ==============================================================================
# Fix & Run Camera Pipeline (services.face-ai)
# Thesis: Edge-based Open-Set Face Recognition on NVIDIA Jetson Orin Nano
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Dừng container mediamtx nếu đang chạy để giải phóng 100% CPU/GPU cho DeepStream
docker stop open_set_fr_mediamtx 2>/dev/null || true

# Kích hoạt virtualenv nếu có
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
elif [ -f "$HOME/.venv/bin/activate" ]; then
    source "$HOME/.venv/bin/activate"
fi

# Thiết lập PYTHONPATH
export PYTHONPATH="${PROJECT_ROOT}:${PROJECT_ROOT}/services/face-ai:${HOME}/open-set-face-recognition:${PYTHONPATH}"

# 1. Chạy fix cấu hình và chuyển hướng cổng 5444 -> 5432
python3 "$PROJECT_ROOT/scripts/fix_face_ai_config.py"

# 2. Khởi chạy pipeline camera
echo ""
echo "===================================================================="
echo "  🚀 KHỞI CHẠY PIPELINE CAMERA AI (services.face-ai.app.main)"
echo "===================================================================="
python3 -m services.face-ai.app.main

