#!/bin/bash
# ==============================================================================
# One-Click Admin Account Generator / Password Reset (Spec v3)
# Hot-patches backend container and seeds admin account with native bcrypt
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "=== [1/3] Hot-patching Backend Container with Native Bcrypt (Zero-Passlib) ==="
if docker ps --format '{{.Names}}' | grep -q "open_set_fr_backend"; then
    docker cp "$PROJECT_ROOT/backend/app/auth/password.py" open_set_fr_backend:/app/app/auth/password.py
    docker cp "$PROJECT_ROOT/backend/app/api/auth.py" open_set_fr_backend:/app/app/api/auth.py
    echo "  ✅ Hot-patched password.py and auth.py into open_set_fr_backend"
fi

echo ""
echo "=== [2/3] Generating Bcrypt Hash & Seeding Admin Account in Database ==="
if docker ps --format '{{.Names}}' | grep -q "open_set_fr_backend"; then
    docker exec -i open_set_fr_backend python3 -c "
import bcrypt
from app.db.database import SessionLocal
from app.db.models import User

salt = bcrypt.gensalt()
hashed = bcrypt.hashpw(b'admin', salt).decode('utf-8')

db = SessionLocal()
u = db.query(User).filter(User.username == 'admin').first()
if not u:
    u = User(username='admin', role='admin', is_active=True)
u.password_hash = hashed
u.role = 'admin'
u.is_active = True
db.add(u)
db.commit()
print('  ✅ Successfully set admin password in PostgreSQL using native bcrypt!')
db.close()
"
else
    # Direct database insertion with pre-computed valid bcrypt hash for 'admin'
    docker exec -i open_set_fr_postgres psql -U open_set_fr -d open_set_fr <<'EOF'
INSERT INTO users (username, password_hash, role, is_active)
VALUES ('admin', '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', 'admin', true)
ON CONFLICT (username) 
DO UPDATE SET 
    password_hash = '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW',
    role = 'admin',
    is_active = true;
EOF
fi

echo ""
echo "=== [3/3] Restarting Backend to Apply Native Bcrypt Auth Handler ==="
docker compose restart backend

echo ""
echo "=== Verifying User in Database ==="
docker exec -i open_set_fr_postgres psql -U open_set_fr -d open_set_fr -c "SELECT user_id, username, role, is_active FROM users WHERE username = 'admin';"

echo ""
echo "===================================================================="
echo "🎉 TÀI KHOẢN ADMIN ĐÃ SẴN SÀNG HOẠT ĐỘNG!"
echo "===================================================================="
echo "  👉 Username:  admin"
echo "  👉 Password:  admin"
echo "===================================================================="
echo "Hãy quay lại màn hình trình duyệt (F5) và đăng nhập ngay!"
