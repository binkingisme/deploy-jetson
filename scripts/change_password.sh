#!/bin/bash
# ==============================================================================
# Password Reset Tool & Security Hot-Patch
# Thesis: Edge-based Open-Set Face Recognition on NVIDIA Jetson Orin Nano
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

USER_TARGET="${1:-admin}"
NEW_PASS="$2"

if [ -z "$NEW_PASS" ]; then
    echo "===================================================================="
    echo "  🔐 ĐỔI MẬT KHẨU TÀI KHOẢN TRÊN NVIDIA JETSON DASHBOARD"
    echo "===================================================================="
    echo "Đang đổi mật khẩu cho tài khoản: [ $USER_TARGET ]"
    read -rsp "Nhập mật khẩu mới mong muốn: " NEW_PASS
    echo ""
    if [ -z "$NEW_PASS" ]; then
        echo "❌ Mật khẩu không được để trống!"
        exit 1
    fi
fi

echo ""
echo ">> [1/4] Khóa cứng Backend: Loại bỏ vĩnh viễn backdoor tự động reset mật khẩu..."
if docker ps --format '{{.Names}}' | grep -q "open_set_fr_backend"; then
    docker cp "$PROJECT_ROOT/backend/app/api/auth.py" open_set_fr_backend:/app/app/api/auth.py
    docker cp "$PROJECT_ROOT/backend/app/auth/password.py" open_set_fr_backend:/app/app/auth/password.py
    echo "  ✅ Đã chép nóng auth.py sạch vào Backend container."
fi

echo ">> [2/4] Đồng bộ giao diện sạch vào Frontend container..."
if docker ps --format '{{.Names}}' | grep -q "open_set_fr_frontend"; then
    docker cp "$PROJECT_ROOT/frontend/dist/." open_set_fr_frontend:/usr/share/nginx/html/ 2>/dev/null || true
    echo "  ✅ Đã đồng bộ giao diện sạch vào Frontend container."
fi

echo ">> [3/4] Cập nhật mật khẩu mới bằng Bcrypt trong Database..."
docker exec -e USER_TARGET="$USER_TARGET" -e NEW_PASS="$NEW_PASS" -i open_set_fr_backend python3 -c "
import os, bcrypt
from app.db.database import SessionLocal
from app.db.models import User
from app.auth.password import verify_password

username = os.environ.get('USER_TARGET', 'admin')
new_pw = os.environ.get('NEW_PASS', '')

if not new_pw:
    print('❌ Lỗi: Mật khẩu rỗng!')
    exit(1)

hashed = bcrypt.hashpw(new_pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

db = SessionLocal()
u = db.query(User).filter(User.username.ilike(username)).first()
if not u:
    u = User(username=username, role='admin', is_active=True)
u.password_hash = hashed
u.is_active = True
db.add(u)
db.commit()
db.refresh(u)

is_new_valid = verify_password(new_pw, u.password_hash)
is_old_blocked = not verify_password('nckh@2026', u.password_hash) if new_pw != 'nckh@2026' else False

print(f'  ✅ Đã lưu hash mật khẩu mới cho user [{u.username}]!')
print(f'  🔍 Kiểm thử mật khẩu mới: {\"HỢP LỆ (THÀNH CÔNG)\" if is_new_valid else \"THẤT BẠI\"}')
if new_pw != 'nckh@2026':
    print(f'  🔒 Mật khẩu cũ nckh@2026: {\"ĐÃ BỊ VÔ HIỆU HÓA HOÀN TOÀN\" if is_old_blocked else \"VẪN CÒN HOẠT ĐỘNG\"}')
db.close()
"

echo ">> [4/4] Khởi động lại Backend để nạp code xác thực mới..."
docker compose restart backend >/dev/null 2>&1 || true

echo ""
echo "===================================================================="
echo "🎉 HOÀN TẤT ĐỔI MẬT KHẨU & BẢO VỆ HỆ THỐNG!"
echo "===================================================================="
echo "  👉 Username: $USER_TARGET"
echo "  👉 Mật khẩu: (Đã lưu mật khẩu mới của bạn)"
echo "===================================================================="
echo "Bây giờ bạn hãy quay lại web và đăng nhập bằng MẬT KHẨU MỚI!"
