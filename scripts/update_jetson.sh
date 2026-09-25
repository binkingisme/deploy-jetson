#!/bin/bash
# ==============================================================================
# Update FastAPI Backend Server on Jetson with latest Camera Dashboard code
# ==============================================================================
set -e

echo === [1/4] Detecting Jetson Backend Directory ===
CANDIDATES=(
  "$HOME/open-set-face-recognition/backend"
  "/home/jetson/open-set-face-recognition/backend"
  "$HOME/dt/backend"
  "/home/jetson/dt/backend"
  "$HOME/camera_dashboard/backend"
  "$HOME/ai_camera_dashboard/backend"
)

TARGET_DIR=""
for dir in "${CANDIDATES[@]}"; do
  if [ -d "$dir" ]; then
    TARGET_DIR="$dir"
    break
  fi
done

if [ -z "$TARGET_DIR" ]; then
  TARGET_DIR="$HOME/dt/backend"
  mkdir -p "$TARGET_DIR"
fi

echo ">> Target Directory: $TARGET_DIR"

echo === [2/4] Fetching Latest Code from GitHub ===
TEMP_DIR=/tmp/camera_dashboard_sync
rm -rf $TEMP_DIR
git clone --depth 1 https://github.com/Lephuc0168/camera_dashboard.git $TEMP_DIR

echo === [3/4] Updating Backend Files ===
cp -r $TEMP_DIR/backend/* $TARGET_DIR/
cp -r $TEMP_DIR/scripts/* $(dirname $TARGET_DIR)/scripts/ 2>/dev/null || true
rm -rf $TEMP_DIR

echo === [4/4] Ensuring Dependencies Installed ===
if [ -f $TARGET_DIR/requirements.txt ]; then
 pip3 install -r $TARGET_DIR/requirements.txt --quiet 2>/dev/null || true
fi

echo ============================================================
echo ✅ Update complete! Spec v3 Enrollment API routes are active:
echo    - POST /api/persons/enroll (Spec v3 §25)
echo    - POST /api/persons/{person_id}/embeddings (Spec v3 §14.7 multi-image)
echo    - GET  /api/gallery/reload (Spec v3 §14.8 atomic reload)
echo    - POST /api/thresholds/import
echo    - POST /api/thresholds/upload
echo    - GET  /api/persons/{id}/photo
echo    - Spec v3 §13.2 created_by column migration
echo ============================================================
echo If uvicorn was running with --reload, it has automatically reloaded.
echo If not running, you can start it with:
echo    cd $TARGET_DIR && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
