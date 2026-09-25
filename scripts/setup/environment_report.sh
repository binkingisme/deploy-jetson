#!/usr/bin/env bash
# ============================================================
# Collect system environment info on the Jetson (Phase 0).
# Writes environment-report.txt in the current directory.
# ============================================================
set -euo pipefail

OUT="environment-report.txt"

{
  echo "=== Jetson System Environment Report ==="
  echo "Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo

  echo "--- JetPack / L4T ---"
  if [ -f /etc/nv_tegra_release ]; then
    cat /etc/nv_tegra_release
  elif command -v dpkg-query >/dev/null 2>&1; then
    dpkg-query -W -f='${Version}\n' nvidia-l4t-core 2>/dev/null || echo "(L4T not found)"
  else
    echo "(unavailable)"
  fi
  echo

  echo "--- CUDA ---"
  if command -v nvcc >/dev/null 2>&1; then
    nvcc --version
  else
    echo "(nvcc not found)"
  fi
  echo

  echo "--- TensorRT ---"
  if [ -f /usr/lib/x86_64-linux-gnu/libnvinfer.so* ] || ls /usr/lib/aarch64-linux-gnu/libnvinfer.so* >/dev/null 2>&1; then
    dpkg-query -W -f='${Version}\n' libnvinfer* 2>/dev/null | head -1 || echo "(found lib, version unknown)"
  else
    echo "(TensorRT lib not found)"
  fi
  echo

  echo "--- DeepStream ---"
  if command -v deepstream-app >/dev/null 2>&1; then
    deepstream-app --version
  elif [ -d /opt/nvidia/deepstream/deepstream ]; then
    cat /opt/nvidia/deepstream/deepstream/RELEASE 2>/dev/null || echo "(deepstream dir present)"
  else
    echo "(not found)"
  fi
  echo

  echo "--- Python ---"
  python3 --version
  echo

  echo "--- Docker ---"
  docker --version 2>/dev/null || echo "(not found)"
  echo

  echo "--- NVIDIA Container Toolkit ---"
  nvidia-ctk --version 2>/dev/null || echo "(not found)"
  echo

  echo "--- Storage ---"
  df -h / 2>/dev/null
} | tee "$OUT"

echo
echo "Report written to: $OUT"
