#!/usr/bin/env python3
"""
Diagnostic & Inspection Script for Jetson PostgreSQL Database
Thesis: Edge-based Open-Set Face Recognition (Spec Section 13)
"""
import os
import sys

def run_inspection():
    print("=" * 65)
    print("  🔍 KIỂM TRA TỔNG QUAN DATABASE JETSON (open_set_fr)")
    print("=" * 65)

    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError:
        print("[INFO] Đang cài đặt psycopg2-binary...")
        os.system("pip3 install psycopg2-binary --quiet")
        import psycopg2
        from psycopg2.extras import RealDictCursor

    CANDIDATE_DBS = [
        os.getenv("DATABASE_URL"),
        "postgresql://open_set_fr:open_set_fr_pass@localhost:5432/open_set_fr",
        "postgresql://open_set_fr:nckh%402026@localhost:5432/open_set_fr",
        "postgresql://open_set_fr:open_set_fr@localhost:5432/open_set_fr",
        "postgresql://postgres:postgres@localhost:5432/open_set_fr",
        "dbname=open_set_fr user=open_set_fr",
        "dbname=open_set_fr user=postgres",
        "dbname=open_set_fr",
    ]

    conn = None
    connected_url = None
    for url in CANDIDATE_DBS:
        if not url:
            continue
        try:
            conn = psycopg2.connect(url)
            connected_url = url
            break
        except Exception:
            continue

    if not conn:
        print("[LỖI] Không thể kết nối tới PostgreSQL trên localhost:5432!")
        print("Gợi ý: Kiểm tra service bằng lệnh: sudo systemctl status postgresql")
        return

    print("[*] Kết nối thành công tới Database!")
    display_conn = connected_url.split('@')[-1] if '@' in connected_url else connected_url
    print(f"[*] Connection: {display_conn}\n")

    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 1. Danh sách các bảng
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name;
    """)
    tables = [r['table_name'] for r in cur.fetchall()]
    print(f"📊 [1] CÁC BẢNG TRONG DATABASE ({len(tables)} bảng):")
    print(f"   {', '.join(tables) if tables else '(Chưa có bảng nào)'}\n")

    # 2. Số lượng bản ghi từng bảng
    print("📈 [2] SỐ LƯỢNG BẢN GHI THEO TỪNG BẢNG:")
    spec_tables = ['users', 'persons', 'face_embeddings', 'identity_thresholds', 'cameras', 'recognition_events']
    for t in spec_tables:
        if t in tables:
            cur.execute(f"SELECT COUNT(*) as cnt FROM {t};")
            count = cur.fetchone()['cnt']
            print(f"   • Bảng '{t}': {count} bản ghi")
        else:
            print(f"   • Bảng '{t}': [CHƯA TẠO]")
    print()

    # 3. Chi tiết bảng users
    if 'users' in tables:
        cur.execute("SELECT user_id, username, role, is_active, created_at FROM users ORDER BY created_at ASC;")
        users = cur.fetchall()
        print(f"👤 [3] DANH SÁCH TÀI KHOẢN USERS ({len(users)} tài khoản):")
        for u in users:
            status = "Active" if u['is_active'] else "Disabled"
            print(f"   • Username: {u['username']:<15} | Role: {u['role']:<10} | Trạng thái: {status}")
        print()

    # 4. Chi tiết bảng identity_thresholds
    if 'identity_thresholds' in tables:
        cur.execute("""
            SELECT threshold_type, COUNT(*) as cnt, AVG(threshold_value) as avg_thr
            FROM identity_thresholds 
            GROUP BY threshold_type;
        """)
        thr_stats = cur.fetchall()
        print("🎯 [4] THỐNG KÊ NGƯỠNG NHẬN DIỆN EVT (identity_thresholds):")
        for s in thr_stats:
            print(f"   • Kiểu ngưỡng: {s['threshold_type']:<15} | Số lượng: {s['cnt']} | Ngưỡng TB: {float(s['avg_thr']):.4f}")
        
        cur.execute("""
            SELECT t.threshold_id, p.full_name, t.threshold_type, t.threshold_value, t.fit_status, t.fallback_used
            FROM identity_thresholds t
            LEFT JOIN persons p ON t.identity_id = p.person_id
            LIMIT 5;
        """)
        sample_thrs = cur.fetchall()
        if sample_thrs:
            print("   Mẫu 5 bản ghi ngưỡng đầu tiên:")
            for st in sample_thrs:
                name = st['full_name'] or 'Global Fallback'
                print(f"   - {name:<20}: {st['threshold_value']:.3f} ({st['threshold_type']}, status={st['fit_status']})")
        print()

    # 5. Chi tiết bảng persons & face_embeddings
    if 'persons' in tables:
        cur.execute("""
            SELECT p.person_id, p.full_name, p.student_code, p.status, p.created_by, COUNT(f.embedding_id) as emb_count
            FROM persons p
            LEFT JOIN face_embeddings f ON p.person_id = f.person_id
            GROUP BY p.person_id, p.full_name, p.student_code, p.status, p.created_by
            ORDER BY p.created_at DESC
            LIMIT 5;
        """)
        persons = cur.fetchall()
        print(f"👥 [5] DANH SÁCH ĐỐI TƯỢNG (persons) (Mẫu 5 người mới nhất):")
        for p in persons:
            code = p['student_code'] or 'N/A'
            creator = f" (Tạo bởi: {str(p['created_by'])[:8]}...)" if p.get('created_by') else ""
            print(f"   • {p['full_name']:<22} | Mã: {code:<12} | Status: {p['status']} | Vectors: {p['emb_count']}{creator}")
        print()

    # 6. Chi tiết bảng cameras
    if 'cameras' in tables:
        cur.execute("SELECT camera_id, camera_code, name, source_type, is_active FROM cameras;")
        cams = cur.fetchall()
        print(f"📹 [6] DANH SÁCH CAMERA ({len(cams)} camera):")
        for c in cams:
            print(f"   • [{c['camera_code']}] {c['name']} ({c['source_type']}) - {'Active' if c['is_active'] else 'Inactive'}")
        print()

    print("=" * 65)
    print("  ✅ Kiểm tra hoàn tất! Database hoạt động bình thường.")
    print("=" * 65)

    cur.close()
    conn.close()

if __name__ == "__main__":
    run_inspection()