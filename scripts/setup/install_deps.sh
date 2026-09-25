#!/usr/bin/env bash
# ============================================================
# Install Python dependencies for the face-ai service (Phase 0).
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "=== Installing system prerequisites ==="
sudo apt-get update
sudo apt-get install -y \
  python3-pip \
  python3-opencv \
  libgomp1

echo "=== Installing Python dependencies ==="
pip install --upgrade pip
pip install -r "$ROOT/services/face-ai/requirements.txt"

echo "=== Installing PostgreSQL client driver ==="
pip install psycopg2-binary

echo "=== Done ==="
