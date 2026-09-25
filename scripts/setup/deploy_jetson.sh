#!/usr/bin/env bash
# ============================================================
# Deploy script — run ON THE JETSON.
# One-shot: build engines -> setup DB -> import gallery+thresholds
#
# Usage:
#   bash scripts/setup/deploy_jetson.sh              # default
#   bash scripts/setup/deploy_jetson.sh --skip-models # skip engine build
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

SKIP_MODELS=false
for arg in "$@"; do
  case "$arg" in
    --skip-models) SKIP_MODELS=true ;;
  esac
done

echo "=================================================="
echo " Deploy Open-Set Face Recognition on Jetson"
echo "   Root: $ROOT"
echo "=================================================="

if [ "$SKIP_MODELS" = false ]; then
  echo
  echo "[1/4] Building TensorRT engines (ONNX -> engine)..."
  # Ensure trtexec exists (JetPack installs TensorRT but not always the binary on PATH)
  if ! command -v trtexec >/dev/null 2>&1 \
     && [ ! -x /usr/src/tensorrt/bin/trtexec ] \
     && [ ! -x /opt/nvidia/tensorrt/bin/trtexec ]; then
    echo "  -> trtexec missing, installing TensorRT tooling..."
    sudo apt-get install -y tensorrt tensorrt-libs
  fi
  bash scripts/model/build_engines.sh
else
  echo
  echo "[1/4] Skipping engine build (--skip-models)"
fi

echo
echo "[2/4] Setting up PostgreSQL + migrations..."
bash scripts/setup/setup_postgres.sh

# Guess parquet/threshold locations
PARQUET="${PARQUET_PATH:-}"
if [ -z "$PARQUET" ]; then
  for cand in known_embeddings.parquet jetson_deploy_v2/known_embeddings.parquet; do
    [ -f "$cand" ] && PARQUET="$cand" && break
  done
fi
THRESH="${THRESHOLD_PATH:-}"
if [ -z "$THRESH" ]; then
  for cand in threshold_table.json thresholds/threshold_table.json jetson_deploy_v2/threshold_table.json; do
    [ -f "$cand" ] && THRESH="$cand" && break
  done
fi

echo
if [ -n "$PARQUET" ]; then
  echo "[3/4] Importing gallery from $PARQUET ..."
  python3 scripts/gallery/build_gallery.py --input "$PARQUET"
else
  echo "[3/4] No parquet found. Skipping gallery import (run later with --input)."
fi

if [ -n "$THRESH" ]; then
  echo "[4/4] Copying threshold table $THRESH -> thresholds/threshold_table.json"
  mkdir -p thresholds
  cp "$THRESH" thresholds/threshold_table.json
else
  echo "[4/4] No threshold table found. Skip."
fi

echo
echo "=================================================="
echo " Deploy step complete."
echo " Next: configure camera + run the pipeline (see docs/DEPLOY_JETSON.md)."
echo "=================================================="