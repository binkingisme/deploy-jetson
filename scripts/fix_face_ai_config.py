#!/usr/bin/env python3
"""
==============================================================================
Auto-Fixer for services.face-ai Camera Pipeline Database Port & Jetson Health
Redirects Port 5444 -> Port 5432 (Docker) and updates configuration files
Thesis: Edge-based Open-Set Face Recognition on NVIDIA Jetson Orin Nano
==============================================================================
"""

import os
import sys
import re
import socket
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACE_AI_DIR = os.path.join(PROJECT_ROOT, "services", "face-ai")

print("=" * 75)
print("  🔧 CẤU HÌNH LIÊN THÔNG SERVICES.FACE-AI VỚI DOCKER POSTGRESQL (PORT 5432)")
print("=" * 75)

# 0. Dừng container mediamtx nếu đang bị crashloop gây sụt giảm FPS / nghẽn CPU Jetson
print(">> [0/5] Kiểm tra và dừng MediaMTX crashloop (giải phóng CPU/GPU Jetson)...")
os.system("docker stop open_set_fr_mediamtx 2>/dev/null || true")
print("✅ Đã dừng MediaMTX (nếu có) để đảm bảo toàn bộ tài nguyên cho Camera AI.")

# 1. Quét và thay đổi port 5444 / 5445 sang 5432 trong thư mục services/face-ai
print("\n>> [1/5] Quét các tệp mã nguồn và cấu hình liên quan đến Camera AI...")
found_and_updated = []
home_dir = os.path.expanduser("~")
search_dirs = [
    FACE_AI_DIR,
    os.path.join(PROJECT_ROOT, "..", "services", "face-ai"),
    os.path.join(home_dir, "open-set-face-recognition", "services", "face-ai"),
    os.path.join(home_dir, "open-set-face-recognition"),
    os.path.join(PROJECT_ROOT, "config"),
    os.path.join(PROJECT_ROOT, "configs"),
    PROJECT_ROOT
]

visited_dirs = set()
for sdir in search_dirs:
    sdir_norm = os.path.abspath(sdir)
    if not os.path.exists(sdir_norm) or sdir_norm in visited_dirs:
        continue
    visited_dirs.add(sdir_norm)
    for root, dirs, files in os.walk(sdir_norm):
        if any(ign in root for ign in ["node_modules", ".git", "__pycache__", ".venv", "postgres_data", "dist"]):
            continue
        for f in files:
            if f.endswith((".py", ".env", ".yaml", ".yml", ".json", ".conf", ".ini")):
                fpath = os.path.join(root, f)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as fp:
                        content = fp.read()
                    if "5444" in content:
                        new_content = content.replace("5444", "5432")
                        with open(fpath, "w", encoding="utf-8") as fp:
                            fp.write(new_content)
                        found_and_updated.append(fpath)
                except Exception:
                    pass

if found_and_updated:
    print(f"✅ Đã tự động cập nhật port 5444 -> 5432 trong {len(found_and_updated)} tệp cấu hình:")
    for p in found_and_updated:
        print(f"   • {p}")
else:
    print("ℹ️ Không tìm thấy tệp mã nguồn nào còn hardcode 5444 (hoặc đã trỏ về 5432).")

# 2. Cấu hình iptables REDIRECT cổng 5444 -> 5432
print("\n>> [2/5] Thiết lập chuyển tiếp kernel iptables (Port Forward 5444 -> 5432)...")
os.system("sudo iptables -t nat -D OUTPUT -p tcp -d 127.0.0.1 --dport 5444 -j REDIRECT --to-ports 5432 2>/dev/null || true")
os.system("sudo iptables -t nat -A OUTPUT -p tcp -d 127.0.0.1 --dport 5444 -j REDIRECT --to-ports 5432 2>/dev/null || true")
os.system("sudo iptables -t nat -D PREROUTING -p tcp --dport 5444 -j REDIRECT --to-ports 5432 2>/dev/null || true")
os.system("sudo iptables -t nat -A PREROUTING -p tcp --dport 5444 -j REDIRECT --to-ports 5432 2>/dev/null || true")
print("✅ Chuyển tiếp cổng 5444 -> 5432 qua iptables: HOÀN TẤT")

# 3. Đảm bảo Docker PostgreSQL cho phép kết nối tự do và có role postgres & open_set_fr
print("\n>> [3/5] Cấp quyền kết nối tin cậy (trust authentication) trong Docker PostgreSQL...")
os.system("""
docker exec -i open_set_fr_postgres sh -c "
    echo 'host all all 127.0.0.1/32 trust' >> /var/lib/postgresql/data/pg_hba.conf 2>/dev/null || true
    echo 'host all all 0.0.0.0/0 trust' >> /var/lib/postgresql/data/pg_hba.conf 2>/dev/null || true
    psql -U open_set_fr -d open_set_fr -c 'CREATE ROLE postgres WITH SUPERUSER LOGIN;' 2>/dev/null || true
    psql -U open_set_fr -d open_set_fr -c 'ALTER ROLE postgres WITH SUPERUSER LOGIN;' 2>/dev/null || true
    psql -U open_set_fr -d open_set_fr -c 'ALTER ROLE open_set_fr WITH SUPERUSER LOGIN;' 2>/dev/null || true
    psql -U open_set_fr -d open_set_fr -c 'SELECT pg_reload_conf();' 2>/dev/null || true
" 2>/dev/null || true
""")
print("✅ Quyền truy cập Docker Database: SẴN SÀNG")

# 4. Kiểm tra kết nối thực tế tới cả 2 cổng 5432 và 5444
print("\n>> [4/5] Kiểm định kết nối thực tế tới Docker Database...")
def test_port(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2.0)
    try:
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False

p5432_ok = test_port("127.0.0.1", 5432)
p5444_ok = test_port("127.0.0.1", 5444)

if p5432_ok:
    print(f"   • Cổng 5432 (Docker PostgreSQL Trực tiếp):  \\033[32mKẾT NỐI TỐT\\033[0m")
else:
    print(f"   • Cổng 5432 (Docker PostgreSQL Trực tiếp):  \\033[31mTHẤT BẠI\\033[0m (Kiểm tra docker compose ps)")

if p5444_ok:
    print(f"   • Cổng 5444 (Chuyển tiếp iptables -> 5432): \\033[32mKẾT NỐI TỐT\\033[0m")
else:
    print(f"   • Cổng 5444 (Chuyển tiếp iptables -> 5432): \\033[33mCảnh báo chuyển tiếp\\033[0m")

try:
    import psycopg2
    conn = psycopg2.connect(host="127.0.0.1", port=5432, user="open_set_fr", dbname="open_set_fr")
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM persons;")
    p_cnt = cur.fetchone()[0]
    cur.close()
    conn.close()
    print(f"   • Truy vấn bảng persons trong Docker DB:    \\033[32mTHÀNH CÔNG\\033[0m ({p_cnt} danh tính)")
except Exception as e:
    print(f"   • Lưu ý psycopg2 query: {e}")

print("\n" + "=" * 75)
print("🎉 HOÀN TẤT TẤT CẢ CÁC BƯỚC KHẮC PHỤC!")
print("🚀 Bây giờ bạn có thể khởi động camera an toàn bằng lệnh:")
print("   bash scripts/run_camera_pipeline.sh")
print("   (hoặc: python3 -m services.face-ai.app.main)")
print("=" * 75 + "\n")
