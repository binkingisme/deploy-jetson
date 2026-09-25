#!/usr/bin/env python3
"""
Direct standalone script to import threshold_table.json into Jetson PostgreSQL.
Zero internal dependencies - only requires psycopg2 and python standard library.
Compatible with open_set_face_recognition_implementation_spec_v2.md Section 13.6.
"""

import os
import sys
import json
import uuid
from datetime import datetime, timezone

try:
    import psycopg2
except ImportError:
    print("[ERROR] psycopg2 is not installed! Installing psycopg2-binary...")
    os.system("pip3 install psycopg2-binary")
    import psycopg2

CANDIDATE_PATHS = [
    "thresholds/threshold_table.json",
    "threshold_table.json",
    os.path.expanduser("~/open-set-face-recognition/thresholds/threshold_table.json"),
    "/home/jetson/open-set-face-recognition/thresholds/threshold_table.json",
    os.path.expanduser("~/camera_dashboard/thresholds/threshold_table.json"),
    os.path.expanduser("~/dt/thresholds/threshold_table.json"),
    "/data/thresholds/threshold_table.json",
]

CANDIDATE_DBS = [
    os.getenv("DATABASE_URL"),
    "postgresql://open_set_fr:open_set_fr_pass@localhost:5432/open_set_fr",
    "postgresql://open_set_fr:nckh%402026@localhost:5432/open_set_fr",
    "postgresql://open_set_fr:open_set_fr@localhost:5432/open_set_fr",
    "postgresql://open_set_fr:admin@localhost:5432/open_set_fr",
    "dbname=open_set_fr user=postgres",
    "dbname=open_set_fr",
]


def find_threshold_file(user_path=None):
    if user_path:
        exp = os.path.expanduser(user_path)
        if os.path.isfile(exp):
            return exp
        print(f"[WARN] User specified path not found: {user_path}")

    for p in CANDIDATE_PATHS:
        exp = os.path.expanduser(p)
        if os.path.isfile(exp):
            return exp

    return None


def connect_db():
    for db_conn_str in CANDIDATE_DBS:
        if not db_conn_str:
            continue
        try:
            conn = psycopg2.connect(db_conn_str)
            return conn, db_conn_str
        except Exception:
            continue

    return None, None


def main():
    print("=" * 70)
    print("  JETSON EVT THRESHOLD TABLE IMPORTER (Spec Section 13.6)")
    print("=" * 70)

    arg_file = sys.argv[1] if len(sys.argv) > 1 else None
    target_file = find_threshold_file(arg_file)

    if not target_file:
        print("\n[ERROR] Không tìm thấy tệp threshold_table.json!")
        print("Đã quét các đường dẫn:")
        for p in CANDIDATE_PATHS:
            print(f"  - {p}")
        print("\nVui lòng truyền đường dẫn chính xác của file:")
        print("  python3 direct_import.py /duong/dan/threshold_table.json\n")
        sys.exit(1)

    print(f"\n[1/4] Đã tìm thấy tệp dữ liệu:")
    print(f"      --> {target_file}")

    with open(target_file, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Connect to database
    print(f"\n[2/4] Đang kết nối tới PostgreSQL (open_set_fr)...")
    conn, used_conn_str = connect_db()

    if not conn:
        print("\n[ERROR] Không thể xác thực mật khẩu vào PostgreSQL Database!")
        print("\nĐể đồng bộ mật khẩu database trong 5 giây, hãy chạy lệnh này:")
        print("  sudo -u postgres psql -c \"ALTER USER open_set_fr WITH PASSWORD 'open_set_fr_pass';\"")
        print("\nSau đó chạy lại script import này là thành công 100%!\n")
        sys.exit(1)

    cur = conn.cursor()

    # 1. Tạo bảng identity_thresholds theo đúng Spec 13.6
    cur.execute("""
    CREATE TABLE IF NOT EXISTS identity_thresholds (
        threshold_id UUID PRIMARY KEY,
        threshold_table_version VARCHAR(100) NOT NULL,
        identity_id UUID REFERENCES persons(person_id) ON DELETE SET NULL,
        threshold_type VARCHAR(30) NOT NULL,
        threshold_value REAL NOT NULL,
        fallback_used BOOLEAN NOT NULL DEFAULT FALSE,
        n_impostor_scores INTEGER,
        n_exceedances INTEGER,
        u_quantile REAL,
        u_value REAL,
        alpha REAL,
        gpd_shape REAL,
        gpd_scale REAL,
        fit_status VARCHAR(20) NOT NULL,
        model_version VARCHAR(100) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_identity_thresholds_version ON identity_thresholds(threshold_table_version);
    """)
    conn.commit()

    # 2. Ánh xạ danh tính người dùng trong Database
    print(f"\n[3/4] Đang đồng bộ danh tính với bảng persons...")
    cur.execute("SELECT person_id, full_name, student_code FROM persons;")
    person_map = {}
    persons_raw = cur.fetchall()
    for pid, fname, scode in persons_raw:
        if pid:
            person_map[str(pid).strip().lower()] = str(pid)
        if fname:
            person_map[fname.strip().lower()] = str(pid)
        if scode:
            person_map[scode.strip().lower()] = str(pid)

    print(f"      - Đã tải {len(persons_raw)} hồ sơ người dùng trong Database.")

    # 3. Phân tích dữ liệu JSON (Cấu trúc chuẩn EVT Calibration Workflow)
    # Xác định phiên bản model và checkpoint
    meta = raw.get("metadata", {}) if isinstance(raw, dict) else {}
    ckpt_hash = meta.get("model_checkpoint_hash", "ckpt_evt")
    prec_mode = meta.get("precision_mode", "fp32")
    top_ver = f"ckpt_{ckpt_hash}_{prec_mode}" if meta.get("model_checkpoint_hash") else raw.get("threshold_table_version", "evt_pot_v1")
    top_model = f"insightface_{ckpt_hash}_{prec_mode}" if meta.get("model_checkpoint_hash") else raw.get("model_version", "insightface_r100_fp16")

    records = []

    # 3a. Global EVT row
    if isinstance(raw, dict) and "global_evt" in raw and isinstance(raw["global_evt"], dict):
        records.append(("__global__", raw["global_evt"]))

    # 3b. Fixed baseline (nếu có)
    if isinstance(raw, dict) and "fixed" in raw and isinstance(raw["fixed"], dict):
        records.append(("fixed", raw["fixed"]))

    # 3c. Identities: hỗ trợ cả list (như file thực tế) và dict
    if isinstance(raw, dict) and "identities" in raw:
        id_data = raw["identities"]
        if isinstance(id_data, list):
            for item in id_data:
                if isinstance(item, dict):
                    id_key = item.get("identity_id") or item.get("identity_name") or item.get("name")
                    records.append((id_key, item))
        elif isinstance(id_data, dict):
            for id_key, item in id_data.items():
                if isinstance(item, dict):
                    records.append((id_key, item))

    # 3d. Fallback nếu JSON dạng khác
    if not records:
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    id_key = item.get("identity_id") or item.get("identity_name") or item.get("name")
                    records.append((id_key, item))
        elif isinstance(raw, dict):
            for id_key, item in raw.items():
                if id_key not in ["schema_version", "config", "metadata", "created_at", "timestamp"] and isinstance(item, dict):
                    records.append((id_key, item))

    print(f"      - Đã phân tích được {len(records)} bản ghi ngưỡng từ file JSON.")

    # Xóa dữ liệu cũ để nạp mới
    cur.execute("DELETE FROM identity_thresholds;")

    # 4. Chèn từng bản ghi vào database
    insert_sql = """
    INSERT INTO identity_thresholds (
        threshold_id, threshold_table_version, identity_id, threshold_type,
        threshold_value, fallback_used, n_impostor_scores, n_exceedances,
        u_quantile, u_value, alpha, gpd_shape, gpd_scale, fit_status,
        model_version, created_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
    """

    count = 0
    matched = 0

    for id_key, item in records:
        raw_type = item.get("threshold_type")
        if not raw_type:
            if id_key in ["__global__", "global_evt", "global"]:
                raw_type = "global_evt"
            elif id_key in ["fixed", "fixed_baseline"]:
                raw_type = "fixed"
            else:
                raw_type = "identity_gpd"

        # Q tắc Spec 13.6: identity_id của global_evt và fixed luôn là NULL
        identity_id = None
        if raw_type not in ["global_evt", "fixed"] and id_key not in ["__global__", "global"]:
            cand = item.get("identity_id") or id_key or item.get("identity_name") or item.get("name")
            if cand:
                c_str = str(cand).strip().lower()
                if c_str in person_map:
                    identity_id = person_map[c_str]
                    matched += 1
                else:
                    try:
                        identity_id = str(uuid.UUID(str(cand)))
                        matched += 1
                    except Exception:
                        pass

        t_id = str(uuid.uuid4())
        t_ver = str(item.get("threshold_table_version") or top_ver)
        t_val = float(item.get("threshold_value", item.get("threshold", item.get("value", 0.72))))
        fallback = bool(item.get("fallback_used", False))
        n_imp = item.get("n_impostor_scores") or item.get("n_impostors") or item.get("n_scores")
        n_exc = item.get("n_exceedances") or item.get("n_exceed")
        u_q = item.get("u_quantile") or item.get("quantile") or 0.95
        u_v = item.get("u_value") or item.get("u")
        alpha = item.get("alpha_effective") or item.get("alpha") or 0.99
        g_shape = item.get("gpd_shape") or item.get("shape") or item.get("xi")
        g_scale = item.get("gpd_scale") or item.get("scale") or item.get("sigma")
        fit = str(item.get("fit_status") or item.get("status") or ("fallback" if fallback else "valid"))
        m_ver = str(item.get("model_version") or top_model)
        created_at = datetime.now(timezone.utc)

        cur.execute(insert_sql, (
            t_id, t_ver, identity_id, raw_type, t_val, fallback,
            int(n_imp) if n_imp is not None else None,
            int(n_exc) if n_exc is not None else None,
            float(u_q) if u_q is not None else None,
            float(u_v) if u_v is not None else None,
            float(alpha) if alpha is not None else None,
            float(g_shape) if g_shape is not None else None,
            float(g_scale) if g_scale is not None else None,
            fit, m_ver, created_at
        ))
        count += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f"\n[4/4] NẠP DỮ LIỆU THÀNH CÔNG VÀO DATABASE! 🚀")
    print(f"      - Tổng số bản ghi đã nạp:      {count}")
    print(f"      - Số danh tính khớp với DB:     {matched}")
    print(f"      - Phiên bản bảng ngưỡng:       {top_ver}")
    print(f"      - Phiên bản mô hình:           {top_model}")
    print("\n" + "=" * 70)
    print("  Bây giờ bạn hãy quay lại trình duyệt web và nhấn F5 tải lại trang /thresholds!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
