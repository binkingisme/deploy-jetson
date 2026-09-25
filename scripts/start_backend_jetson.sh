#!/bin/bash
# ==============================================================================
# Start FastAPI Backend Server connected to Jetson PostgreSQL Database
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")/backend"

cd "$BACKEND_DIR"

echo "=== Installing Python dependencies (if needed) ==="
pip install -r requirements.txt

echo "=== Starting FastAPI Server on port 8000 ==="
export DATABASE_URL="postgresql://open_set_fr:open_set_fr_pass@localhost:5432/open_set_fr"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
