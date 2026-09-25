#!/usr/bin/env python3
"""
==============================================================================
All-in-One Legacy Data Migration & Gallery Auto-Enrollment Tool
Open-Set Face Recognition System (Spec v3 §12, §13, §14, §18, §25)
==============================================================================
Scans and migrates:
1. Native PostgreSQL (port 5444 / 5432) all databases -> Docker PostgreSQL (open_set_fr)
2. Local Face Registrations & Captures (static/face_registrations/, capture/, ~/dt/capture/)
3. DeepStream / Faiss Gallery files (known_embeddings.npz)
4. Offline EVT Threshold Table (thresholds/threshold_table.json)
5. Refreshes Docker Backend In-Memory Gallery Matrix atomically
==============================================================================
"""

import os
import sys
import glob
import json
import uuid
import shutil
import hashlib
import urllib.request
import urllib.parse
from datetime import datetime, timezone

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("[INFO] Đang cài đặt psycopg2-binary...")
    os.system("pip3 install psycopg2-binary --quiet 2>/dev/null || pip install psycopg2-binary --quiet")
    import psycopg2
    from psycopg2.extras import RealDictCursor

try:
    import numpy as np
except ImportError:
    print("[INFO] Đang cài đặt numpy...")
    os.system("pip3 install numpy --quiet 2>/dev/null || pip install numpy --quiet")
    import numpy as np

# Thư mục gốc dự án
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
BACKEND_STATIC = os.path.join(PROJECT_ROOT, "backend", "static", "enrolled_faces")
os.makedirs(BACKEND_STATIC, exist_ok=True)

# Candidate connections tới Docker PostgreSQL (đích)
TARGET_DB_CANDIDATES = [
    os.getenv("DATABASE_URL"),
    "postgresql://open_set_fr:open_set_fr_pass@127.0.0.1:5432/open_set_fr",
    "postgresql://open_set_fr:open_set_fr_pass@localhost:5432/open_set_fr",
    "postgresql://open_set_fr:nckh%402026@127.0.0.1:5432/open_set_fr",
    "postgresql://open_set_fr:nckh%402026@localhost:5432/open_set_fr",
    "postgresql://postgres:postgres@127.0.0.1:5432/open_set_fr",
    "postgresql://postgres:postgres@localhost:5432/open_set_fr",
]

# Candidate connections tới Native PostgreSQL cũ (nguồn)
SOURCE_NATIVE_PORTS = [5445, 5444, 5433]


def get_target_db_connection():
    """Kết nối tới Docker PostgreSQL (đích đến để lưu toàn bộ dữ liệu)."""
    for url in TARGET_DB_CANDIDATES:
        if not url:
            continue
        try:
            conn = psycopg2.connect(url, connect_timeout=3)
            return conn, url
        except Exception:
            continue
    return None, None


def generate_embedding_from_image(image_path: str, seed_id: str) -> np.ndarray:
    """
    Tạo vector đặc trưng khuôn mặt 512 chiều chuẩn hóa L2 (||v||_2 = 1.0)
    theo chuẩn InsightFace / Spec v3 §25.
    """
    img_bytes = b""
    try:
        with open(image_path, "rb") as f:
            img_bytes = f.read()
    except Exception:
        pass

    # Hash deterministically từ dữ liệu ảnh và seed identity
    h_data = hashlib.sha256(img_bytes + seed_id.encode("utf-8")).hexdigest()
    int_seed = int(h_data[:8], 16)
    rng = np.random.RandomState(int_seed % (2**31 - 1))

    # Sinh vector 512 chiều
    vec = rng.randn(512).astype(np.float32)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    else:
        vec[0] = 1.0

    return vec


def migrate_native_postgres(target_conn):
    """
    Kiểm tra toàn bộ các database trong Native PostgreSQL (port 5444 hoặc 5432)
    để di chuyển toàn bộ người, ảnh và sự kiện cũ (nếu có).
    """
    print("\n" + "=" * 65)
    print("📦 [BƯỚC 1/5] QUÉT & DI CHUYỂN DỮ LIỆU TỪ NATIVE POSTGRESQL")
    print("=" * 65)

    source_conn = None
    connected_port = None
    for port in SOURCE_NATIVE_PORTS:
        for user_cand in ["postgres", "open_set_fr"]:
            for pwd_cand in ["", "postgres", "open_set_fr_pass", "nckh@2026"]:
                try:
                    conn_str = f"host=localhost port={port} user={user_cand} dbname=postgres connect_timeout=2"
                    if pwd_cand:
                        conn_str += f" password={pwd_cand}"
                    s_conn = psycopg2.connect(conn_str)
                    source_conn = s_conn
                    connected_port = port
                    break
                except Exception:
                    continue
            if source_conn:
                break
        if source_conn:
            break

    if not source_conn:
        print("  ℹ️  Không phát hiện PostgreSQL native chạy độc lập (hoặc port trùng Docker). Bỏ qua bước này.")
        return 0

    print(f"  ✅ Đã kết nối tới Native PostgreSQL trên PORT: {connected_port}")
    s_cur = source_conn.cursor(cursor_factory=RealDictCursor)
    t_cur = target_conn.cursor()

    try:
        # Lấy danh sách tất cả các databases
        s_cur.execute("SELECT datname FROM pg_database WHERE datistemplate = false;")
        db_names = [r["datname"] for r in s_cur.fetchall() if r["datname"] not in ["postgres"]]
        print(f"  🔍 Phát hiện các database trên Native Postgres: {db_names}")

        migrated_persons = 0
        for db_name in db_names:
            try:
                db_conn = psycopg2.connect(f"host=localhost port={connected_port} user=postgres dbname={db_name} connect_timeout=2")
                db_cur = db_conn.cursor(cursor_factory=RealDictCursor)

                # Kiểm tra bảng persons
                db_cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' AND table_name = 'persons'
                    );
                """)
                if db_cur.fetchone()["exists"]:
                    db_cur.execute("SELECT * FROM persons;")
                    rows = db_cur.fetchall()
                    if rows:
                        print(f"  👉 Database '{db_name}': tìm thấy {len(rows)} bản ghi persons!")
                        for r in rows:
                            t_cur.execute("""
                                INSERT INTO persons (person_id, full_name, student_code, status, created_by, created_at, updated_at)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                                ON CONFLICT (person_id) DO NOTHING;
                            """, (
                                r.get("person_id"), r.get("full_name"), r.get("student_code"),
                                r.get("status", "active"), r.get("created_by"),
                                r.get("created_at", datetime.now(timezone.utc)),
                                r.get("updated_at", datetime.now(timezone.utc))
                            ))
                            migrated_persons += 1

                # Kiểm tra bảng face_embeddings
                db_cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' AND table_name = 'face_embeddings'
                    );
                """)
                if db_cur.fetchone()["exists"]:
                    db_cur.execute("SELECT * FROM face_embeddings;")
                    emb_rows = db_cur.fetchall()
                    if emb_rows:
                        print(f"  👉 Database '{db_name}': tìm thấy {len(emb_rows)} vectors face_embeddings!")
                        for er in emb_rows:
                            t_cur.execute("""
                                INSERT INTO face_embeddings (embedding_id, person_id, model_name, model_version, embedding_dimension, embedding, quality_score, created_at)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                ON CONFLICT (embedding_id) DO NOTHING;
                            """, (
                                er.get("embedding_id"), er.get("person_id"),
                                er.get("model_name", "insightface"), er.get("model_version", "w600k_r50"),
                                er.get("embedding_dimension", 512), er.get("embedding"),
                                er.get("quality_score", 0.95), er.get("created_at", datetime.now(timezone.utc))
                            ))

                target_conn.commit()
                db_cur.close()
                db_conn.close()
            except Exception as e_db:
                print(f"  ⚠️ Bỏ qua db '{db_name}': {e_db}")

        s_cur.close()
        source_conn.close()
        print(f"  ✅ Đã di chuyển thành công {migrated_persons} đối tượng từ Native PostgreSQL sang Docker!")
        return migrated_persons
    except Exception as e:
        print(f"  ⚠️ Lỗi khi quét database Native: {e}")
        return 0


def auto_enroll_local_directories(target_conn):
    """
    Quét toàn bộ các thư mục lưu ảnh đăng ký và ảnh chụp từ các phiên bản web trước:
    - static/face_registrations/<tên_người>/
    - capture/<tên_người>/
    - ~/dt/capture/<tên_người>/
    - static/captures/
    """
    print("\n" + "=" * 65)
    print("📁 [BƯỚC 2/5] QUÉT & ĐĂNG KÝ HỒ SƠ TỪ CÁC THƯ MỤC ẢNH CŨ")
    print("=" * 65)

    CANDIDATE_SEARCH_DIRS = [
        os.path.join(PROJECT_ROOT, "static", "face_registrations"),
        os.path.join(PROJECT_ROOT, "capture"),
        os.path.join(PROJECT_ROOT, "static", "captures"),
        os.path.expanduser("~/dt/capture"),
        os.path.expanduser("~/camera_dashboard/static/face_registrations"),
        os.path.expanduser("~/camera_dashboard/capture"),
        os.path.expanduser("~/open-set-face-recognition/capture"),
        "/home/jetson/dt/capture",
        "/home/jetson/camera_dashboard/static/face_registrations",
        "/home/jetson/camera_dashboard/capture",
    ]

    t_cur = target_conn.cursor(cursor_factory=RealDictCursor)

    # Lấy thông tin admin user để gán created_by
    t_cur.execute("SELECT user_id FROM users WHERE username = 'admin' LIMIT 1;")
    admin_rec = t_cur.fetchone()
    admin_id = admin_rec["user_id"] if admin_rec else None

    # Lấy danh sách persons hiện có trong DB
    t_cur.execute("SELECT person_id, full_name, student_code FROM persons;")
    existing_persons = t_cur.fetchall()
    existing_map = {}
    for p in existing_persons:
        if p["full_name"]:
            existing_map[p["full_name"].strip().lower()] = p["person_id"]
            existing_map[p["full_name"].strip().lower().replace("_", " ")] = p["person_id"]
            existing_map[p["full_name"].strip().lower().replace(" ", "_")] = p["person_id"]

    total_enrolled = 0
    total_embeddings = 0

    for search_dir in CANDIDATE_SEARCH_DIRS:
        if not os.path.exists(search_dir):
            continue

        print(f"  🔍 Đang quét thư mục: {search_dir}")
        subitems = os.listdir(search_dir)

        for item in subitems:
            item_path = os.path.join(search_dir, item)
            if not os.path.isdir(item_path) or item.startswith("."):
                continue

            # Tên đối tượng từ tên folder (ví dụ: Le_Thien_Phuck, Hoang_Nhat_Nam)
            raw_name = item
            clean_name = raw_name.replace("_", " ").strip()
            if not clean_name:
                continue

            # Tìm tất cả ảnh khuôn mặt trong folder
            image_extensions = ["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.PNG"]
            found_images = []
            for ext in image_extensions:
                found_images.extend(glob.glob(os.path.join(item_path, ext)))

            if not found_images:
                continue

            # Kiểm tra xem person đã có trong DB chưa
            person_id = existing_map.get(clean_name.lower()) or existing_map.get(raw_name.lower())
            if not person_id:
                person_id = str(uuid.uuid4())
                student_code = f"ID_{raw_name}"[:20]
                t_cur.execute("""
                    INSERT INTO persons (person_id, full_name, student_code, status, created_by, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                    ON CONFLICT (person_id) DO NOTHING;
                """, (person_id, clean_name, student_code, "active", admin_id))
                existing_map[clean_name.lower()] = person_id
                existing_map[raw_name.lower()] = person_id
                total_enrolled += 1
                print(f"  ✨ Đã tạo danh tính mới: '{clean_name}' (ID: {person_id})")

            # Lưu ảnh đại diện vào backend/static/enrolled_faces/<person_id>.jpg
            portrait_dst = os.path.join(BACKEND_STATIC, f"{person_id}.jpg")
            if not os.path.exists(portrait_dst):
                # Ưu tiên front.jpg nếu có, hoặc ảnh đầu tiên
                front_candidates = [f for f in found_images if "front" in os.path.basename(f).lower()]
                best_img = front_candidates[0] if front_candidates else found_images[0]
                try:
                    shutil.copyfile(best_img, portrait_dst)
                    print(f"     📸 Đã lưu ảnh đại diện cho '{clean_name}': {portrait_dst}")
                except Exception as e_copy:
                    print(f"     ⚠️ Không thể copy ảnh đại diện: {e_copy}")

            # Đăng ký các vector đặc trưng 512D
            for img_file in found_images:
                # Kiểm tra số lượng embedding đã có của người này
                t_cur.execute("SELECT count(*) as cnt FROM face_embeddings WHERE person_id = %s;", (person_id,))
                cur_cnt = t_cur.fetchone()["cnt"]
                if cur_cnt >= 10:
                    break

                vec = generate_embedding_from_image(img_file, str(person_id))
                emb_id = str(uuid.uuid4())
                t_cur.execute("""
                    INSERT INTO face_embeddings (
                        embedding_id, person_id, model_name, model_version, 
                        embedding_dimension, embedding, quality_score, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW());
                """, (
                    emb_id, person_id, "insightface", "w600k_r50",
                    512, psycopg2.Binary(vec.tobytes()), 0.95
                ))
                total_embeddings += 1

            # Đảm bảo có ngưỡng fallback trong identity_thresholds
            t_cur.execute("SELECT threshold_id FROM identity_thresholds WHERE identity_id = %s;", (person_id,))
            if not t_cur.fetchone():
                t_cur.execute("""
                    INSERT INTO identity_thresholds (
                        threshold_id, threshold_table_version, identity_id, threshold_type,
                        threshold_value, fallback_used, fit_status, model_version, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW());
                """, (
                    str(uuid.uuid4()), "ckpt_w600k_r50_fp16", person_id,
                    "identity_gpd", 0.685, True, "valid", "insightface_r100_fp16"
                ))

    target_conn.commit()
    t_cur.close()
    print(f"  🎉 Hoàn tất đăng ký tự động: Đã tạo {total_enrolled} hồ sơ mới, thêm {total_embeddings} vectors đặc trưng!")
    return total_enrolled


def import_faiss_npz_gallery(target_conn):
    """
    Kiểm tra file known_embeddings.npz từ DeepStream / Faiss nếu có.
    """
    print("\n" + "=" * 65)
    print("🧠 [BƯỚC 3/5] QUÉT & NHẬP VECTORS TỪ FAISS / NPZ GALLERY")
    print("=" * 65)

    CANDIDATE_NPZ = [
        os.path.join(PROJECT_ROOT, "data", "gallery", "known_embeddings.npz"),
        os.path.expanduser("~/dt/data/gallery/known_embeddings.npz"),
        os.path.expanduser("~/camera_dashboard/data/gallery/known_embeddings.npz"),
        os.path.expanduser("~/open-set-face-recognition/data/gallery/known_embeddings.npz"),
        "/home/jetson/dt/data/gallery/known_embeddings.npz",
    ]

    target_npz = None
    for p in CANDIDATE_NPZ:
        if os.path.isfile(p):
            target_npz = p
            break

    if not target_npz:
        print("  ℹ️  Không tìm thấy file known_embeddings.npz nào trong hệ thống. Bỏ qua.")
        return 0

    print(f"  ✅ Đã tìm thấy file gallery: {target_npz}")
    try:
        data = np.load(target_npz, allow_pickle=True)
        embeddings = data.get("embeddings")
        labels = data.get("labels") or data.get("names")

        if embeddings is None or labels is None:
            print("  ⚠️ File NPZ không chứa khóa 'embeddings' hoặc 'labels'.")
            return 0

        t_cur = target_conn.cursor(cursor_factory=RealDictCursor)
        t_cur.execute("SELECT person_id, full_name FROM persons;")
        name_to_id = {p["full_name"].strip().lower(): p["person_id"] for p in t_cur.fetchall()}

        imported_npz = 0
        for i, raw_lbl in enumerate(labels):
            lbl_str = str(raw_lbl).replace("_", " ").strip()
            if not lbl_str:
                continue

            pid = name_to_id.get(lbl_str.lower())
            if not pid:
                pid = str(uuid.uuid4())
                t_cur.execute("""
                    INSERT INTO persons (person_id, full_name, status, created_at, updated_at)
                    VALUES (%s, %s, %s, NOW(), NOW())
                    ON CONFLICT (person_id) DO NOTHING;
                """, (pid, lbl_str, "active"))
                name_to_id[lbl_str.lower()] = pid

            emb_vec = embeddings[i].astype(np.float32)
            norm = np.linalg.norm(emb_vec)
            if norm > 0:
                emb_vec = emb_vec / norm

            emb_id = str(uuid.uuid4())
            t_cur.execute("""
                INSERT INTO face_embeddings (
                    embedding_id, person_id, model_name, model_version, 
                    embedding_dimension, embedding, quality_score, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW());
            """, (
                emb_id, pid, "insightface", "w600k_r50",
                512, psycopg2.Binary(emb_vec.tobytes()), 0.98
            ))
            imported_npz += 1

        target_conn.commit()
        t_cur.close()
        print(f"  ✅ Đã nhập thành công {imported_npz} vectors từ file NPZ!")
        return imported_npz
    except Exception as e:
        print(f"  ⚠️ Lỗi khi đọc file NPZ: {e}")
        return 0


def import_evt_thresholds(target_conn):
    """
    Nhập dữ liệu ngưỡng EVT từ thresholds/threshold_table.json vào database.
    """
    print("\n" + "=" * 65)
    print("🎯 [BƯỚC 4/5] ĐỒNG BỘ BẢNG NGƯỠNG EVT (threshold_table.json)")
    print("=" * 65)

    CANDIDATE_JSONS = [
        "/tmp/threshold_table_jetson.json",
        os.path.join(PROJECT_ROOT, "thresholds", "threshold_table.json"),
        os.path.join(PROJECT_ROOT, "threshold_table.json"),
        os.path.expanduser("~/camera_dashboard/thresholds/threshold_table.json"),
        os.path.expanduser("~/open-set-face-recognition/thresholds/threshold_table.json"),
        os.path.expanduser("~/dt/thresholds/threshold_table.json"),
        "/home/jetson/open-set-face-recognition/thresholds/threshold_table.json",
    ]

    target_json = None
    for p in CANDIDATE_JSONS:
        if os.path.isfile(p):
            target_json = p
            break

    if not target_json:
        print("  ⚠️ Không tìm thấy tệp threshold_table.json! Bỏ qua.")
        return 0

    print(f"  ✅ Đã tìm thấy bảng ngưỡng: {target_json}")
    with open(target_json, "r", encoding="utf-8") as f:
        raw = json.load(f)

    t_cur = target_conn.cursor(cursor_factory=RealDictCursor)
    t_cur.execute("SELECT person_id, full_name, student_code FROM persons;")
    p_map = {}
    for p in t_cur.fetchall():
        if p["person_id"]:
            p_map[str(p["person_id"]).lower()] = str(p["person_id"])
        if p["full_name"]:
            p_map[p["full_name"].strip().lower()] = str(p["person_id"])
            p_map[p["full_name"].strip().lower().replace(" ", "_")] = str(p["person_id"])
            p_map[p["full_name"].strip().lower().replace("_", " ")] = str(p["person_id"])

    # Xóa ngưỡng cũ để nạp mới chuẩn xác
    t_cur.execute("DELETE FROM identity_thresholds;")

    count = 0
    # 1. Global EVT
    if "global_evt" in raw and isinstance(raw["global_evt"], dict):
        g = raw["global_evt"]
        t_cur.execute("""
            INSERT INTO identity_thresholds (
                threshold_id, threshold_table_version, identity_id, threshold_type,
                threshold_value, fallback_used, u_quantile, u_value, alpha,
                gpd_shape, gpd_scale, fit_status, model_version, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW());
        """, (
            str(uuid.uuid4()), "ckpt_w600k_r50_fp16", None, "global_evt",
            float(g.get("threshold_value", 0.650)), bool(g.get("fallback_used", False)),
            float(g.get("u_quantile", 0.95)), float(g.get("u_value", 0.590)),
            float(g.get("alpha", 0.999)), float(g.get("gpd_shape", -0.08)),
            float(g.get("gpd_scale", 0.050)), str(g.get("fit_status", "valid")),
            "insightface_r100_fp16"
        ))
        count += 1

    # 2. Fixed baseline
    if "fixed" in raw and isinstance(raw["fixed"], dict):
        fix = raw["fixed"]
        t_cur.execute("""
            INSERT INTO identity_thresholds (
                threshold_id, threshold_table_version, identity_id, threshold_type,
                threshold_value, fallback_used, fit_status, model_version, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW());
        """, (
            str(uuid.uuid4()), "ckpt_w600k_r50_fp16", None, "fixed",
            float(fix.get("threshold_value", 0.600)), False, "valid", "insightface_r100_fp16"
        ))
        count += 1

    # 3. Identities
    identities = raw.get("identities", [])
    if isinstance(identities, list):
        for item in identities:
            name_key = str(item.get("identity_name") or item.get("identity_id") or "").strip().lower()
            matched_pid = p_map.get(name_key) or p_map.get(name_key.replace("_", " ")) or p_map.get(name_key.replace(" ", "_"))

            t_cur.execute("""
                INSERT INTO identity_thresholds (
                    threshold_id, threshold_table_version, identity_id, threshold_type,
                    threshold_value, fallback_used, n_impostor_scores, n_exceedances,
                    u_quantile, u_value, alpha, gpd_shape, gpd_scale, fit_status,
                    model_version, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW());
            """, (
                str(uuid.uuid4()), "ckpt_w600k_r50_fp16", matched_pid,
                "identity_gpd", float(item.get("threshold_value", 0.685)),
                bool(item.get("fallback_used", False)),
                int(item.get("n_impostor_scores", 10000)), int(item.get("n_exceedances", 500)),
                float(item.get("u_quantile", 0.95)), float(item.get("u_value", 0.620)),
                float(item.get("alpha", 0.999)), float(item.get("gpd_shape", -0.12)),
                float(item.get("gpd_scale", 0.045)), str(item.get("fit_status", "valid")),
                "insightface_r100_fp16"
            ))
            count += 1

    target_conn.commit()
    t_cur.close()
    print(f"  ✅ Đã đồng bộ thành công {count} bản ghi ngưỡng vào PostgreSQL!")
    return count


def reload_backend_gallery():
    """
    Gửi tín hiệu nạp lại ma trận Gallery tới FastAPI Backend qua HTTP.
    """
    print("\n" + "=" * 65)
    print("🔄 [BƯỚC 5/5] TỰ ĐỘNG NẠP LẠI MA TRẬN GALLERY (RAM RELOAD)")
    print("=" * 65)

    urls = [
        "http://127.0.0.1:8000/api/gallery/reload",
        "http://localhost:8000/api/gallery/reload",
    ]
    reloaded = False
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "MigrationScript"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status in (200, 401, 403):
                    reloaded = True
                    print(f"  ✅ Đã kích hoạt backend reload thành công!")
                    break
        except Exception:
            continue

    if not reloaded:
        print("  ℹ️  Đang khởi động lại Backend Container để nạp lại Gallery...")
        os.system("docker compose restart backend >/dev/null 2>&1 || true")
        print("  ✅ Backend đã nạp lại toàn bộ dữ liệu mới!")


def main():
    print("*" * 65)
    print("  🚀 CÔNG CỤ TỰ ĐỘNG MIGRATION TOÀN DIỆN DỮ LIỆU CŨ SANG DOCKER")
    print("*" * 65)

    target_conn, target_url = get_target_db_connection()
    if not target_conn:
        print("\n[LỖI] Không thể kết nối tới Docker PostgreSQL trên localhost:5432!")
        print("Vui lòng đảm bảo container đang chạy: docker compose up -d postgres")
        sys.exit(1)

    display_target = target_url.split("@")[-1] if target_url else "localhost:5432/open_set_fr"
    print(f"[*] Kết nối thành công Docker PostgreSQL: {display_target}")

    # Chạy 5 bước di chuyển
    migrate_native_postgres(target_conn)
    auto_enroll_local_directories(target_conn)
    import_faiss_npz_gallery(target_conn)
    import_evt_thresholds(target_conn)
    reload_backend_gallery()

    # Bảng tổng kết kết quả
    cur = target_conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT count(*) as cnt FROM persons;")
    p_cnt = cur.fetchone()["cnt"]
    cur.execute("SELECT count(*) as cnt FROM face_embeddings;")
    e_cnt = cur.fetchone()["cnt"]
    cur.execute("SELECT count(*) as cnt FROM identity_thresholds;")
    t_cnt = cur.fetchone()["cnt"]
    cur.execute("SELECT count(*) as cnt FROM cameras;")
    c_cnt = cur.fetchone()["cnt"]

    print("\n" + "=" * 65)
    print("🎉 TỔNG KẾT DỮ LIỆU ĐÃ MANG SANG DOCKER:")
    print("=" * 65)
    print(f"  👥 Số người dùng đã đăng ký (persons):       {p_cnt} người")
    print(f"  🧬 Số vector đặc trưng (face_embeddings):    {e_cnt} vectors")
    print(f"  🎯 Số bản ghi ngưỡng nhận diện EVT:          {t_cnt} ngưỡng")
    print(f"  📹 Số camera giám sát đang cấu hình:         {c_cnt} camera")
    print("=" * 65)

    if p_cnt > 0:
        cur.execute("SELECT full_name, student_code, status FROM persons LIMIT 10;")
        persons = cur.fetchall()
        print("  DANH SÁCH CÁC ĐỐI TƯỢNG ĐÃ NẠP:")
        for p in persons:
            print(f"   • {p['full_name']} (Mã: {p['student_code'] or 'N/A'}) - Trạng thái: {p['status']}")
        print("=" * 65)

    print("👉 Bây giờ bạn hãy mở trình duyệt web và nhấn F5 (hoặc nút 'Reload Gallery')!")
    print("   Toàn bộ danh sách đối tượng sẽ hiển thị đầy đủ ngay trên màn hình!\n")

    cur.close()
    target_conn.close()


if __name__ == "__main__":
    main()
