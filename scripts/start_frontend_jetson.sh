#!/bin/bash
# ==============================================================================
# Start React Vite Frontend Server
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(dirname "$SCRIPT_DIR")/frontend"

cd "$FRONTEND_DIR"

echo "=== Installing npm dependencies (if needed) ==="
npm install

echo "=== Starting Vite Frontend Dev Server on port 3000 ==="
npm run dev
