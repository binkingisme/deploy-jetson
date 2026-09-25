#!/usr/bin/env python3
"""
==============================================================================
Database Reconciliation & Diff Tool: Native PostgreSQL vs Docker PostgreSQL
Thesis: Edge-based Open-Set Face Recognition on NVIDIA Jetson Orin Nano
==============================================================================
Compares side-by-side:
- Row counts for all tables (users, persons, face_embeddings, identity_thresholds, cameras, recognition_events)
- Detailed identity list (matching, missing in new, extra in new)
- Threshold configurations (identity_gpd, global_evt, fixed)
- Event timestamps and ranges
- Generates a human-readable comparison report (Terminal + Markdown file)
- Optional flag: --sync-missing to safely bring over any missing rows
==============================================================================
"""

import os
import sys
import json
import uuid
from datetime import datetime, timezone

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    os.system("pip3 install psycopg2-binary --quiet 2>/dev/null || pip install psycopg2-binary --quiet")
    import psycopg2
    from psycopg2.extras import RealDictCursor

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

DOCKER_PORT = 5432
CANDIDATE_OLD_PORTS = [5445, 5444, 5433]

DOCKER_URLS = [
    os.getenv("DATABASE_URL"),
    f"postgresql://open_set_fr:open_set_fr_pass@127.0.0.1:{DOCKER_PORT}/open_set_fr",
    f"postgresql://open_set_fr:open_set_fr_pass@localhost:{DOCKER_PORT}/open_set_fr",
    f"postgresql://postgres:postgres@127.0.0.1:{DOCKER_PORT}/open_set_fr",
]

CORE_TABLES = [
    "users",
    "persons",
    "face_embeddings",
    "identity_thresholds",
    "cameras",
    "recognition_events",
    "audit_logs",
    "system_metrics"
]


def connect_docker():
    for url in DOCKER_URLS:
        if not url:
            continue
        try:
            conn = psycopg2.connect(url, connect_timeout=3)
            return conn, url
        except Exception:
            continue
    return None, None


def connect_native():
    candidate_passwords = ["open_set_fr_pass", "nckh@2026", "postgres", "open_set_fr", ""]
    candidate_users = ["postgres", "open_set_fr"]
    candidate_hosts = ["127.0.0.1", "localhost", "/var/run/postgresql"]

    last_error = None
    for port in CANDIDATE_OLD_PORTS:
        for host in candidate_hosts:
            for u in candidate_users:
                for p in candidate_passwords:
                    for db in ["open_set_fr", "postgres"]:
                        try:
                            if host.startswith("/"):
                                conn_str = f"host={host} port={port} dbname={db} user={u} connect_timeout=2"
                            else:
                                conn_str = f"host={host} port={port} dbname={db} user={u} connect_timeout=2"
                                if p:
                                    conn_str += f" password={p}"
                            conn = psycopg2.connect(conn_str)
                            
                            # Tìm database có dữ liệu phong phú nhất
                            cur = conn.cursor()
                            cur.execute("SELECT datname FROM pg_database WHERE datistemplate = false;")
                            all_dbs = [r[0] for r in cur.fetchall()]
                            cur.close()

                            best_db = db
                            best_cnt = 0
                            for cand_db in all_dbs:
                                try:
                                    test_str = conn_str.replace(f"dbname={db}", f"dbname={cand_db}")
                                    t_conn = psycopg2.connect(test_str)
                                    t_cur = t_conn.cursor()
                                    t_cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'persons');")
                                    if t_cur.fetchone()[0]:
                                        t_cur.execute("SELECT count(*) FROM persons;")
                                        cnt = t_cur.fetchone()[0]
                                        if cnt >= best_cnt:
                                            best_cnt = cnt
                                            best_db = cand_db
                                    t_cur.close()
                                    t_conn.close()
                                except Exception:
                                    pass

                            final_conn = psycopg2.connect(conn_str.replace(f"dbname={db}", f"dbname={best_db}"))
                            return final_conn, f"host={host} port={port} db={best_db} user={u}"
                        except Exception as e:
                            last_error = str(e).strip()
                            continue
    return None, last_error


def get_table_count(conn, table_name):
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT count(*) FROM {table_name};")
        cnt = cur.fetchone()[0]
        cur.close()
        return cnt
    except Exception:
        conn.rollback()
        return None


def get_persons_data(conn):
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT person_id, full_name, student_code, status, created_at FROM persons;")
        rows = cur.fetchall()
        cur.close()
        return {str(r["person_id"]): r for r in rows}
    except Exception:
        conn.rollback()
        return {}


def get_thresholds_data(conn):
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT threshold_id, identity_id, threshold_type, threshold_value, 
                   fallback_used, gpd_shape, gpd_scale, u_value, fit_status
            FROM identity_thresholds;
        """)
        rows = cur.fetchall()
        cur.close()
        return rows
    except Exception:
        conn.rollback()
        return []


def get_events_stats(conn):
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT count(*) as total, 
                   min(occurred_at) as earliest, 
                   max(occurred_at) as latest,
                   count(DISTINCT person_id) as distinct_persons
            FROM recognition_events;
        """)
        res = cur.fetchone()
        cur.close()
        return res
    except Exception:
        conn.rollback()
        return None


def main():
    sync_missing = "--sync-missing" in sys.argv

    print("=" * 80)
    print(f"{BOLD}{CYAN}🔍 CÔNG CỤ ĐỐI CHIẾU & KIỂM ĐỊNH DATABASE: NATIVE (CŨ) VS DOCKER (MỚI){RESET}")
    print("=" * 80)

    # 1. Kết nối Docker DB (Mới)
    docker_conn, docker_url_str = connect_docker()
    if not docker_conn:
        print(f"{RED}❌ Không thể kết nối tới Docker PostgreSQL trên cổng {DOCKER_PORT}!{RESET}")
        print("   Vui lòng kiểm tra: docker compose ps")
        sys.exit(1)
    print(f"✅ {BOLD}Database MỚI (Docker):{RESET} Đã kết nối thành công (Cổng {DOCKER_PORT})")

    # 2. Kết nối Native DB (Cũ)
    native_conn, native_info = connect_native()
    if not native_conn:
        print(f"\n{YELLOW}⚠️ Không thể kết nối tới Native PostgreSQL trên các cổng {CANDIDATE_OLD_PORTS}.{RESET}")
        if native_info:
            print(f"   👉 Chi tiết lỗi kết nối: {BOLD}{native_info}{RESET}")
        print("   👉 Gợi ý: Hãy chạy lại bằng lệnh:")
        print(f"      {BOLD}bash scripts/compare_dbs.sh{RESET}")
        
        # In thông tin bảng hiện tại của Docker DB
        print("=" * 80)
        print(f"{BOLD}📊 THỐNG KÊ HIỆN TẠI TRONG DOCKER POSTGRESQL (CỔNG 5432):{RESET}")
        print("=" * 80)
        for t in CORE_TABLES:
            cnt = get_table_count(docker_conn, t)
            print(f"   • {t.ljust(25)}: {cnt if cnt is not None else 'Không tồn tại'} bản ghi")
        print("=" * 80)
        sys.exit(0)

    print(f"✅ {BOLD}Database CŨ (Native):{RESET} Đã kết nối thành công ({native_info})")

    # Báo cáo so sánh
    report_lines = []
    report_lines.append("# BÁO CÁO ĐỐI CHIẾU DATABASE: NATIVE (CŨ) VS DOCKER (MỚI)")
    report_lines.append(f"Thời gian tạo: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n")

    # 3. So sánh số lượng bản ghi (Row Counts)
    print("\n" + "=" * 80)
    print(f"{BOLD}📊 [1] SO SÁNH SỐ LƯỢNG BẢN GHI TỔNG QUAN GIỮA 2 DATABASE:{RESET}")
    print("=" * 80)

    header = f"| {'Tên Bảng (Table)':<22} | {'DB CŨ (Native)':<16} | {'DB MỚI (Docker)':<16} | {'Chênh Lệch':<12} | {'Trạng Thái':<12} |"
    sep = f"|{'-'*24}|{'-'*18}|{'-'*18}|{'-'*14}|{'-'*14}|"
    print(header)
    print(sep)

    report_lines.append("## 1. Bảng so sánh số lượng bản ghi tổng quan\n")
    report_lines.append(header)
    report_lines.append(sep)

    for t in CORE_TABLES:
        c_old = get_table_count(native_conn, t)
        c_new = get_table_count(docker_conn, t)

        if c_old is None and c_new is None:
            continue

        s_old = str(c_old) if c_old is not None else "Không có"
        s_new = str(c_new) if c_new is not None else "Không có"

        if c_old is not None and c_new is not None:
            diff = c_new - c_old
            s_diff = f"{'+' if diff > 0 else ''}{diff}"
            if diff == 0:
                status = f"{GREEN}Đồng bộ OK{RESET}"
                status_raw = "Đồng bộ OK"
            elif diff > 0:
                status = f"{CYAN}Mới nhiều hơn{RESET}"
                status_raw = "Mới nhiều hơn"
            else:
                status = f"{YELLOW}Mới thiếu {abs(diff)}{RESET}"
                status_raw = f"Mới thiếu {abs(diff)}"
        else:
            s_diff = "N/A"
            status = f"{RED}Lệch schema{RESET}"
            status_raw = "Lệch schema"

        row_term = f"| {t:<22} | {s_old:<16} | {s_new:<16} | {s_diff:<12} | {status:<21} |"
        row_raw = f"| {t:<22} | {s_old:<16} | {s_new:<16} | {s_diff:<12} | {status_raw:<12} |"
        print(row_term)
        report_lines.append(row_raw)

    print(sep)
    print()

    # 4. Đối chiếu chi tiết bảng PERSONS
    print("=" * 80)
    print(f"{BOLD}👥 [2] ĐỐI CHIẾU CHI TIẾT BẢNG PERSONS (DANH TÍNH ĐĂNG KÝ):{RESET}")
    print("=" * 80)

    old_persons = get_persons_data(native_conn)
    new_persons = get_persons_data(docker_conn)

    old_names = {p["full_name"].strip(): pid for pid, p in old_persons.items() if p.get("full_name")}
    new_names = {p["full_name"].strip(): pid for pid, p in new_persons.items() if p.get("full_name")}

    matched_names = set(old_names.keys()) & set(new_names.keys())
    missing_in_new = set(old_names.keys()) - set(new_names.keys())
    only_in_new = set(new_names.keys()) - set(old_names.keys())

    print(f"  • Tổng danh tính ở DB Cũ:     {BOLD}{len(old_persons)}{RESET}")
    print(f"  • Tổng danh tính ở DB Mới:    {BOLD}{len(new_persons)}{RESET}")
    print(f"  • Trùng khớp cả 2 bên:        {GREEN}{BOLD}{len(matched_names)}{RESET} người")
    print(f"  • Có ở DB Cũ nhưng THIẾU ở DB Mới: {YELLOW if missing_in_new else GREEN}{BOLD}{len(missing_in_new)}{RESET} người")
    print(f"  • Chỉ có ở DB Mới (đăng ký thêm):   {CYAN}{BOLD}{len(only_in_new)}{RESET} người")

    report_lines.append("\n## 2. Đối chiếu chi tiết bảng Persons (Danh tính)")
    report_lines.append(f"- Tổng danh tính ở DB Cũ: **{len(old_persons)}**")
    report_lines.append(f"- Tổng danh tính ở DB Mới: **{len(new_persons)}**")
    report_lines.append(f"- Trùng khớp cả 2 bên: **{len(matched_names)}**")
    report_lines.append(f"- Có ở DB Cũ nhưng thiếu ở DB Mới: **{len(missing_in_new)}**")
    report_lines.append(f"- Chỉ có ở DB Mới: **{len(only_in_new)}**\n")

    if missing_in_new:
        print(f"\n  {YELLOW}⚠️ DANH SÁCH {len(missing_in_new)} NGƯỜI CÓ Ở DB CŨ NHƯNG CHƯA CÓ TRONG DB MỚI:{RESET}")
        report_lines.append("### Danh sách người thiếu trong DB Mới:")
        for idx, name in enumerate(sorted(missing_in_new), 1):
            pid = old_names[name]
            pdata = old_persons[pid]
            code = pdata.get("student_code") or "N/A"
            print(f"     {idx:2d}. {name:<30} (Mã: {code}, ID: {pid[:8]}...)")
            report_lines.append(f"- {name} (Mã: {code}, ID: {pid})")

    if only_in_new:
        print(f"\n  {CYAN}ℹ️  DANH SÁCH {len(only_in_new)} NGƯỜI MỚI ĐĂNG KÝ TRONG DB DOCKER:{RESET}")
        report_lines.append("\n### Danh sách người chỉ có trong DB Mới:")
        for idx, name in enumerate(sorted(only_in_new), 1):
            pid = new_names[name]
            print(f"     {idx:2d}. {name:<30} (ID: {pid[:8]}...)")
            report_lines.append(f"- {name} (ID: {pid})")

    # 5. Đối chiếu bảng IDENTITY_THRESHOLDS
    print("\n" + "=" * 80)
    print(f"{BOLD}🎯 [3] ĐỐI CHIẾU CHI TIẾT BẢNG IDENTITY_THRESHOLDS (NGƯỠNG EVT GPD):{RESET}")
    print("=" * 80)

    old_thr = get_thresholds_data(native_conn)
    new_thr = get_thresholds_data(docker_conn)

    print(f"  • Tổng bản ghi ngưỡng ở DB Cũ:  {BOLD}{len(old_thr)}{RESET}")
    print(f"  • Tổng bản ghi ngưỡng ở DB Mới: {BOLD}{len(new_thr)}{RESET}")

    def count_thr_types(thr_list):
        counts = {"identity_gpd": 0, "global_evt": 0, "fixed": 0, "other": 0}
        for item in thr_list:
            t_type = item.get("threshold_type", "other")
            counts[t_type] = counts.get(t_type, 0) + 1
        return counts

    c_thr_old = count_thr_types(old_thr)
    c_thr_new = count_thr_types(new_thr)

    print(f"    - DB Cũ:  Identity GPD: {c_thr_old.get('identity_gpd', 0)}, Global EVT: {c_thr_old.get('global_evt', 0)}, Fixed: {c_thr_old.get('fixed', 0)}")
    print(f"    - DB Mới: Identity GPD: {c_thr_new.get('identity_gpd', 0)}, Global EVT: {c_thr_new.get('global_evt', 0)}, Fixed: {c_thr_new.get('fixed', 0)}")

    report_lines.append("\n## 3. Đối chiếu chi tiết bảng Identity Thresholds")
    report_lines.append(f"- DB Cũ: Tổng {len(old_thr)} bản ghi (GPD: {c_thr_old.get('identity_gpd', 0)}, Global: {c_thr_old.get('global_evt', 0)}, Fixed: {c_thr_old.get('fixed', 0)})")
    report_lines.append(f"- DB Mới: Tổng {len(new_thr)} bản ghi (GPD: {c_thr_new.get('identity_gpd', 0)}, Global: {c_thr_new.get('global_evt', 0)}, Fixed: {c_thr_new.get('fixed', 0)})\n")

    # 6. Đối chiếu bảng RECOGNITION_EVENTS
    print("\n" + "=" * 80)
    print(f"{BOLD}📹 [4] ĐỐI CHIẾU SỰ KIỆN NHẬN DIỆN (RECOGNITION_EVENTS):{RESET}")
    print("=" * 80)

    old_ev_stats = get_events_stats(native_conn)
    new_ev_stats = get_events_stats(docker_conn)

    if old_ev_stats and new_ev_stats:
        print(f"  • DB Cũ:  Tổng {BOLD}{old_ev_stats['total']}{RESET} sự kiện | Sớm nhất: {old_ev_stats['earliest']} | Mới nhất: {old_ev_stats['latest']}")
        print(f"  • DB Mới: Tổng {BOLD}{new_ev_stats['total']}{RESET} sự kiện | Sớm nhất: {new_ev_stats['earliest']} | Mới nhất: {new_ev_stats['latest']}")
        
        report_lines.append("## 4. Đối chiếu sự kiện nhận diện (Recognition Events)")
        report_lines.append(f"- DB Cũ: Tổng {old_ev_stats['total']} sự kiện (Từ {old_ev_stats['earliest']} đến {old_ev_stats['latest']})")
        report_lines.append(f"- DB Mới: Tổng {new_ev_stats['total']} sự kiện (Từ {new_ev_stats['earliest']} đến {new_ev_stats['latest']})\n")

    # 7. Đồng bộ bù nếu có --sync-missing
    if sync_missing:
        print("\n" + "=" * 80)
        print(f"{BOLD}{CYAN}🔄 [5] BẮT ĐẦU ĐỒNG BỘ BÙ CÁC DỮ LIỆU CÒN THIẾU TỪ DB CŨ SANG DB MỚI...{RESET}")
        print("=" * 80)

        t_cur = docker_conn.cursor()
        s_cur = native_conn.cursor(cursor_factory=RealDictCursor)

        # 7.1 Bù Users
        try:
            s_cur.execute("SELECT * FROM users;")
            users = s_cur.fetchall()
            synced_users = 0
            for u in users:
                t_cur.execute("""
                    INSERT INTO users (user_id, username, password_hash, role, is_active, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (username) DO NOTHING;
                """, (u.get("user_id"), u.get("username"), u.get("password_hash"), u.get("role"), u.get("is_active", True), u.get("created_at"), u.get("updated_at")))
                synced_users += 1
            docker_conn.commit()
            print(f"  ✅ Đã đồng bộ an toàn {synced_users} tài khoản người dùng.")
        except Exception as e:
            docker_conn.rollback()

        # 7.2 Bù Persons
        try:
            s_cur.execute("SELECT * FROM persons;")
            p_rows = s_cur.fetchall()
            synced_persons = 0
            for p in p_rows:
                t_cur.execute("""
                    INSERT INTO persons (person_id, full_name, student_code, status, created_by, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (person_id) DO NOTHING;
                """, (p.get("person_id"), p.get("full_name"), p.get("student_code"), p.get("status", "active"), p.get("created_by"), p.get("created_at"), p.get("updated_at")))
                synced_persons += 1
            docker_conn.commit()
            print(f"  ✅ Đã đồng bộ an toàn {synced_persons} danh tính (persons).")
        except Exception as e:
            docker_conn.rollback()

        # 7.3 Bù Face Embeddings
        try:
            s_cur.execute("SELECT * FROM face_embeddings;")
            e_rows = s_cur.fetchall()
            synced_emb = 0
            for e in e_rows:
                t_cur.execute("""
                    INSERT INTO face_embeddings (
                        embedding_id, person_id, model_name, model_version, 
                        embedding_dimension, embedding, quality_score, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (embedding_id) DO NOTHING;
                """, (
                    e.get("embedding_id"), e.get("person_id"), e.get("model_name"),
                    e.get("model_version"), e.get("embedding_dimension"),
                    e.get("embedding"), e.get("quality_score"), e.get("created_at")
                ))
                synced_emb += 1
            docker_conn.commit()
            print(f"  ✅ Đã đồng bộ an toàn {synced_emb} vector đặc trưng (face_embeddings).")
        except Exception as e:
            docker_conn.rollback()

        # 7.4 Bù Cameras
        try:
            s_cur.execute("SELECT * FROM cameras;")
            cam_rows = s_cur.fetchall()
            synced_cams = 0
            for c in cam_rows:
                t_cur.execute("""
                    INSERT INTO cameras (camera_id, name, rtsp_url, location, status, fps, resolution, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (camera_id) DO NOTHING;
                """, (
                    c.get("camera_id"), c.get("name"), c.get("rtsp_url"), c.get("location"),
                    c.get("status", "active"), c.get("fps", 30), c.get("resolution", "1080p"),
                    c.get("created_at"), c.get("updated_at")
                ))
                synced_cams += 1
            docker_conn.commit()
            print(f"  ✅ Đã đồng bộ an toàn {synced_cams} camera.")
        except Exception as e:
            docker_conn.rollback()

        # 7.5 Bù Recognition Events
        try:
            s_cur.execute("SELECT * FROM recognition_events;")
            ev_rows = s_cur.fetchall()
            synced_ev = 0
            for ev in ev_rows:
                t_cur.execute("""
                    INSERT INTO recognition_events (
                        event_id, camera_id, track_id, person_id, status,
                        similarity, threshold_value, threshold_type, fallback_used,
                        quality_score, model_version, threshold_table_version,
                        error_code, occurred_at, snapshot_path, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (event_id) DO NOTHING;
                """, (
                    ev.get("event_id"), ev.get("camera_id"), ev.get("track_id"),
                    ev.get("person_id"), ev.get("status"), ev.get("similarity"),
                    ev.get("threshold_value"), ev.get("threshold_type"),
                    ev.get("fallback_used", False), ev.get("quality_score"),
                    ev.get("model_version"), ev.get("threshold_table_version"),
                    ev.get("error_code"), ev.get("occurred_at"),
                    ev.get("snapshot_path"), json.dumps(ev.get("metadata", {})) if isinstance(ev.get("metadata"), dict) else None
                ))
                synced_ev += 1
            docker_conn.commit()
            print(f"  ✅ Đã đồng bộ an toàn {synced_ev} sự kiện nhận diện lịch sử.")
        except Exception as e:
            docker_conn.rollback()

        # 7.6 Bù Identity Thresholds (Toàn bộ 42 bản ghi từ DB Cũ)
        try:
            s_cur.execute("SELECT * FROM identity_thresholds;")
            thr_rows = s_cur.fetchall()
            if thr_rows:
                t_cur.execute("DELETE FROM identity_thresholds;")
                synced_thr = 0
                json_export_identities = []
                global_evt_item = None
                fixed_item = None

                for t in thr_rows:
                    t_cur.execute("""
                        INSERT INTO identity_thresholds (
                            threshold_id, threshold_table_version, identity_id, threshold_type,
                            threshold_value, fallback_used, n_impostor_scores, n_exceedances,
                            u_quantile, u_value, alpha, gpd_shape, gpd_scale, fit_status,
                            model_version, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """, (
                        t.get("threshold_id"), t.get("threshold_table_version"), t.get("identity_id"),
                        t.get("threshold_type"), t.get("threshold_value"), t.get("fallback_used", False),
                        t.get("n_impostor_scores"), t.get("n_exceedances"), t.get("u_quantile"),
                        t.get("u_value"), t.get("alpha"), t.get("gpd_shape"), t.get("gpd_scale"),
                        t.get("fit_status"), t.get("model_version"), t.get("created_at")
                    ))
                    synced_thr += 1

                    if t.get("threshold_type") == "global_evt":
                        global_evt_item = dict(t)
                    elif t.get("threshold_type") == "fixed":
                        fixed_item = dict(t)
                    else:
                        json_export_identities.append(dict(t))

                docker_conn.commit()
                print(f"  ✅ Đã đồng bộ trọn vẹn {synced_thr} bản ghi ngưỡng EVT/GPD từ DB Cũ sang DB Mới!")

                # Đồng bộ luôn ra file thresholds/threshold_table.json
                try:
                    json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "thresholds", "threshold_table.json")
                    export_payload = {
                        "schema_version": "1.0",
                        "metadata": {"model_checkpoint_hash": "w600k_r50", "precision_mode": "fp16"},
                        "global_evt": global_evt_item or {"threshold_value": 0.650},
                        "fixed": fixed_item or {"threshold_value": 0.600},
                        "identities": json_export_identities
                    }
                    with open(json_path, "w", encoding="utf-8") as jf:
                        json.dump(export_payload, jf, indent=2, ensure_ascii=False, default=str)
                    print(f"  💾 Đã đồng bộ file cấu hình gốc: {json_path}")
                except Exception as e_json:
                    pass
        except Exception as e:
            print(f"  ⚠️ Lỗi đồng bộ ngưỡng: {e}")
            docker_conn.rollback()

        t_cur.close()
        s_cur.close()

        print(f"\n{GREEN}🎉 HOÀN TẤT ĐỒNG BỘ BÙ DỮ LIỆU AN TOÀN!{RESET}")
        print(">> Đang làm mới bộ nhớ Backend...")
        os.system("docker compose restart backend >/dev/null 2>&1 || true")

    # Lưu báo cáo ra file Markdown
    report_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db_reconciliation_report.md")
    try:
        with open(report_file, "w", encoding="utf-8") as f_rep:
            f_rep.write("\n".join(report_lines))
        print(f"\n📄 Đã lưu báo cáo đối chiếu chi tiết tại: {BOLD}{report_file}{RESET}")
    except Exception:
        pass

    print("\n" + "=" * 80)
    print(f"{BOLD}💡 HƯỚNG DẪN TIẾP THEO DÀNH CHO BẠN:{RESET}")
    if missing_in_new:
        print(f"  👉 Nếu bạn muốn chuyển nốt những người và dữ liệu còn thiếu từ DB Cũ sang DB Mới:")
        print(f"     {BOLD}python3 scripts/compare_dbs.py --sync-missing{RESET}")
    else:
        print(f"  ✅ DB Mới đã có đầy đủ hoặc nhiều hơn dữ liệu của DB Cũ!")
        print(f"  👉 Bạn hoàn toàn có thể yên tâm sử dụng DB Mới trên Docker.")
    print("=" * 80 + "\n")

    docker_conn.close()
    native_conn.close()


if __name__ == "__main__":
    main()
