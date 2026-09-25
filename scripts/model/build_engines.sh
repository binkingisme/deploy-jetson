#!/usr/bin/env bash
# ============================================================
# Build TensorRT engines from ONNX — run ON THE JETSON.
#
# IMPORTANT: TensorRT engines are device-specific. Builds must happen
# on the target Jetson (same GPU + TensorRT version), NOT on a PC.
#
# Produces:
#   models/detector/detector_fp16.engine     <- yolov12n_face.onnx
#   models/recognition/face_recog_fp16.engine <- w600k_r50.onnx
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

DET_ONNX="models/detector/det_10g.onnx"
DET_ENGINE="models/detector/det_10g_fp16.engine"
REC_ONNX="models/recognition/w600k_r50.onnx"
REC_ENGINE="models/recognition/face_recog_fp16.engine"

# ---- locate trtexec (not always on PATH after JetPack install) ----
find_trtexec() {
  if command -v trtexec >/dev/null 2>&1; then
    command -v trtexec
    return 0
  fi
  local paths=(
    /usr/src/tensorrt/bin/trtexec
    /opt/nvidia/tensorrt/bin/trtexec
    /opt/TensorRT/bin/trtexec
    /usr/local/bin/trtexec
  )
  local p
  for p in "${paths[@]}"; do
    if [ -x "$p" ]; then
      echo "$p"
      return 0
    fi
  done
  return 1
}

TRTEXEC="$(find_trtexec || true)"

echo "=================================================="
echo " TensorRT engine builder (run on Jetson)"
if [ -n "$TRTEXEC" ]; then
  echo "   trtexec:      $TRTEXEC"
  echo "   TRT version:  $("$TRTEXEC" --version 2>/dev/null | grep -i 'tensorrt' | head -1)"
else
  echo "   trtexec:      not found in PATH or common locations"
fi
echo "=================================================="

if [ -z "$TRTEXEC" ]; then
  echo
  echo "[ERROR] trtexec not found."
  echo
  echo "  TensorRT is usually installed with JetPack but trtexec is not"
  echo "  always symlinked into /usr/local/bin."
  echo
  echo "  Fix (JetPack 6.2.2 / Ubuntu 22.04):"
  echo "    sudo apt-get install -y tensorrt-libs  # runtime libs"
  echo "    sudo apt-get install -y tensorrt       # including trtexec"
  echo "    # OR on JetPack the binary often lives at /usr/src/tensorrt/bin/trtexec"
  echo
  echo "  Then re-run:  bash scripts/model/build_engines.sh"
  exit 1
fi

# ---- Detection: SCRFD det_10g, [1,3,640,640] dynamic input, 9 outputs ----
# DeepStream nvinfer strips output dim 0 (treats it as batch), so the 2D
# outputs [N,C] must be reshaped to [1,N,C] for full dims/buffers to survive.
DET_ONNX_4D="\$(dirname "$DET_ONNX")/det_10g_4d.onnx"
echo
echo ">>> Building detection engine..."
echo "    $DET_ONNX (4D-ified) -> $DET_ENGINE"
if [ -f "$DET_ONNX" ]; then
  mkdir -p "\$(dirname "$DET_ENGINE")"
  python3 scripts/model/make_onnx_4d.py "$DET_ONNX" "$DET_ONNX_4D"
  "$TRTEXEC" \
    --onnx="$DET_ONNX_4D" \
    --saveEngine="$DET_ENGINE" \
    --fp16 \
    --minShapes=input.1:1x3x640x640 \
    --optShapes=input.1:1x3x640x640 \
    --maxShapes=input.1:1x3x640x640 \
    --memPoolSize=workspace:1024
  echo "    OK: $DET_ENGINE"
else
  echo "    SKIP: $DET_ONNX not found (copy from jetson_deploy_v2/det_10g.onnx)"
fi

# ---- Recognition: w600k_r50, [1,3,112,112] -> [1,512] ----
echo
echo ">>> Building recognition engine..."
echo "    $REC_ONNX -> $REC_ENGINE"
if [ -f "$REC_ONNX" ]; then
  mkdir -p "$(dirname "$REC_ENGINE")"
  "$TRTEXEC" \
    --onnx="$REC_ONNX" \
    --saveEngine="$REC_ENGINE" \
    --fp16 \
    --minShapes=input.1:1x3x112x112 \
    --optShapes=input.1:1x3x112x112 \
    --maxShapes=input.1:1x3x112x112 \
    --memPoolSize=workspace:1024
  echo "    OK: $REC_ENGINE"
else
  echo "    SKIP: $REC_ONNX not found"
fi

echo
echo "=================================================="
echo " Done."
echo " Engines next to ONNX ready for DeepStream:"
echo "   $DET_ENGINE"
echo "   $REC_ENGINE"
echo "=================================================="