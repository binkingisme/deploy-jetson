#!/usr/bin/env python3
"""
==============================================================================
Live Real-Time Recognition Events Sync & Diagnostics Bridge
Thesis: Edge-based Open-Set Face Recognition on NVIDIA Jetson Orin Nano
==============================================================================
1. Diagnoses which port the camera/DeepStream pipeline is writing to (5444, 5445, or 5432).
2. Scans and reports/fixes any config files hardcoding port 5444.
3. Continuously forwards new recognition events from Native Postgres -> Docker Postgres (5432)
   in real-time (every 1s) and broadcasts them to the Web Dashboard WebSocket.
==============================================================================
"""

import os
import sys
import time
import glob
import json
import urllib.request
from datetime import datetime, timezone

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    os.system("pip3 install psycopg2-binary --quiet 2>/dev/null || pip install psycopg2-binary --quiet")
    import psycopg2
    from psycopg2.extras import RealDictCursor

DOCKER_PORT = 5432
CANDIDATE_NATIVE_PORTS = [5444, 5445]

DOCKER_DB_URL = f"postgresql://open_set_fr:open_set_fr_pass@127.0.0.1:{DOCKER_PORT}/open_set_fr"


def connect_db(port, dbname="open_set_fr", user="open_set_fr", password="open_set_fr_pass"):
    candidate_passwords = [password, "nckh@2026", "postgres", ""]
    candidate_users = [user, "postgres"]

    for u in candidate_users:
        for p in candidate_passwords:
            try:
                conn_str = f"host=127.0.0.1 port={port} dbname={dbname} user={u} connect_timeout=2"
                if p:
                    conn_str += f" password={p}"
                conn = psycopg2.connect(conn_str)
                return conn
            except Exception:
                continue
    return None


def get_event_stats(conn):
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT count(*) as cnt, max(occurred_at) as latest FROM recognition_events;")
        res = cur.fetchone()
        cur.close()
        return res["cnt"], res["latest"]
    except Exception:
        return 0, None


def scan_and_report_configs():
    print("\n" + "=" * 65)
    print("🔎 [1/3] QUÉT CÁC FILE CẤU HÌNH CAMERA / RECOGNITION TRÊN JETSON")
    print("=" * 65)

    search_roots = [
        os.path.expanduser("~/open-set-face-recognition"),
        os.path.expanduser("~/dt"),
        os.path.expanduser("~/camera_dashboard"),
        os.getcwd()
    ]

    target_extensions = [".py", ".env", ".yaml", ".yml", ".json", ".sh", ".conf"]
    found_files = []

    for sroot in search_roots:
        if not os.path.exists(sroot):
            continue
        for root, _, files in os.walk(sroot):
            if "node_modules" in root or ".git" in root or "__pycache__" in root:
                continue
            for f in files:
                if any(f.endswith(ext) for ext in target_extensions):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as fp:
                            content = fp.read()
                            if "5444" in content or "5445" in content:
                                found_files.append((fpath, content))
                    except Exception:
                        continue

    if found_files:
        print(f"  👉 Phát hiện {len(found_files)} tệp đang cấu hình kết nối tới cổng 5444/5445:")
        for fp, content in found_files:
            print(f"     • {fp}")
            # Tự động gợi ý hoặc sửa nếu có cờ --fix
            if "--fix" in sys.argv:
                try:
                    new_content = content.replace("5444", "5432").replace("5445", "5432")
                    with open(fp, "w", encoding="utf-8") as out_fp:
                        out_fp.write(new_content)
                    print(f"       ✅ Đã tự động cập nhật cổng sang 5432 (Docker)!")
                except Exception as e:
                    print(f"       ⚠️ Không thể cập nhật: {e}")
        if "--fix" not in sys.argv:
            print("\n  💡 Mẹo: Bạn có thể chạy lại với cờ '--fix' để tự động chuyển toàn bộ về cổng 5432:")
            print("     python3 scripts/diagnose_and_sync_events.py --fix")
    else:
        print("  ℹ️  Không thấy file nào hardcode cổng 5444/5445 trong thư mục quét.")


def run_live_sync_loop(source_port, active_native_conn, docker_conn):
    print("\n" + "=" * 65)
    print(f"🚀 [3/3] BẮT ĐẦU CẦU NỐI ĐỒNG BỘ REAL-TIME (CỔNG {source_port} ➡️ DOCKER 5432)")
    print("=" * 65)
    print("  🟢 Trạng thái: ĐANG CHẠY REAL-TIME (Kiểm tra mỗi 1 giây)...")
    print("  Nhấn Ctrl + C để dừng bridge.\n")

    s_cur = active_native_conn.cursor(cursor_factory=RealDictCursor)
    d_cur = docker_conn.cursor(cursor_factory=RealDictCursor)

    # Lấy mốc thời gian sự kiện mới nhất hiện có trong Docker
    d_cur.execute("SELECT max(occurred_at) as latest FROM recognition_events;")
    last_synced_time = d_cur.fetchone()["latest"]

    while True:
        try:
            # Truy vấn sự kiện mới từ Native PostgreSQL
            if last_synced_time:
                s_cur.execute("""
                    SELECT * FROM recognition_events 
                    WHERE occurred_at > %s 
                    ORDER BY occurred_at ASC 
                    LIMIT 100;
                """, (last_synced_time,))
            else:
                s_cur.execute("SELECT * FROM recognition_events ORDER BY occurred_at DESC LIMIT 50;")

            new_events = s_cur.fetchall()

            if new_events:
                # Đảo lại theo thứ tự thời gian tăng dần
                if not last_synced_time:
                    new_events = list(reversed(new_events))

                inserted_count = 0
                for ev in new_events:
                    try:
                        d_cur.execute("""
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
                        inserted_count += 1
                        last_synced_time = ev.get("occurred_at")
                    except Exception as e_ins:
                        docker_conn.rollback()

                docker_conn.commit()

                if inserted_count > 0:
                    latest_ev = new_events[-1]
                    name_str = f"Person ID: {str(latest_ev.get('person_id'))[:8]}..." if latest_ev.get("person_id") else "UNKNOWN"
                    sim_str = f"{latest_ev.get('similarity'):.2f}" if latest_ev.get("similarity") is not None else "N/A"
                    print(f"  [Live Sync 🟢] +{inserted_count} sự kiện mới ➡️ Docker! Status: {latest_ev.get('status')} | {name_str} | Sim: {sim_str} | Lúc: {latest_ev.get('occurred_at')}")

                    # Thông báo tới backend WebSocket
                    try:
                        req_data = json.dumps({
                            "type": "new_event_alert",
                            "status": latest_ev.get("status"),
                            "track_id": latest_ev.get("track_id"),
                            "similarity": latest_ev.get("similarity"),
                            "occurred_at": str(latest_ev.get("occurred_at"))
                        }).encode("utf-8")
                        req = urllib.request.Request("http://127.0.0.1:8000/api/internal/inference", data=req_data, headers={"Content-Type": "application/json"})
                        urllib.request.urlopen(req, timeout=0.5)
                    except Exception:
                        pass

        except Exception as e_cycle:
            print(f"  ⚠️ Lỗi vòng lặp sync: {e_cycle}")
            time.sleep(2)

        time.sleep(1.0)


def main():
    print("=" * 65)
    print("📊 KIỂM TRA & ĐỒNG BỘ SỰ KIỆN NHẬN DIỆN REAL-TIME (RECOGNITION EVENTS)")
    print("=" * 65)

    # 1. Kiểm tra Docker PostgreSQL
    docker_conn = connect_db(DOCKER_PORT)
    if not docker_conn:
        print("  ❌ Không thể kết nối tới Docker PostgreSQL trên cổng 5432!")
        print("     Hãy đảm bảo container đang chạy: docker compose up -d postgres")
        sys.exit(1)

    d_cnt, d_latest = get_event_stats(docker_conn)
    print(f"  🐳 Docker PostgreSQL (Cổng {DOCKER_PORT}):")
    print(f"     • Số sự kiện hiện có:  {d_cnt} sự kiện")
    print(f"     • Sự kiện mới nhất:    {d_latest or 'Chưa có'}")

    # 2. Kiểm tra Native PostgreSQL
    active_native_conn = None
    active_native_port = None
    max_native_cnt = -1

    for p in CANDIDATE_NATIVE_PORTS:
        n_conn = connect_db(p)
        if n_conn:
            n_cnt, n_latest = get_event_stats(n_conn)
            print(f"  💻 Native PostgreSQL (Cổng {p}):")
            print(f"     • Số sự kiện hiện có:  {n_cnt} sự kiện")
            print(f"     • Sự kiện mới nhất:    {n_latest or 'Chưa có'}")

            if n_cnt > max_native_cnt and n_cnt > 0:
                max_native_cnt = n_cnt
                active_native_conn = n_conn
                active_native_port = p

    # Quét các file cấu hình
    scan_and_report_configs()

    # Báo cáo kết luận
    print("\n" + "=" * 65)
    print("📋 [2/3] KẾT LUẬN NGUYÊN NHÂN")
    print("=" * 65)
    if active_native_port and max_native_cnt > d_cnt:
        print(f"  🎯 PHÁT HIỆN: Camera/Inference pipeline đang ghi sự kiện vào CỔNG NATIVE {active_native_port}!")
        print(f"     (Cổng {active_native_port} có {max_native_cnt} sự kiện, trong khi Docker cổng 5432 mới có {d_cnt} sự kiện).")
        print(f"     Đó là lý do tại sao màn hình web (đọc từ Docker 5432) không tự cập nhật theo thời gian thực!")
    elif active_native_port:
        print(f"  👉 Cổng {active_native_port} đang mở. Sẽ thiết lập cầu nối đồng bộ liên tục sang Docker!")
    else:
        print("  ℹ️  Native Postgres hiện không có sự kiện mới hơn Docker.")

    # 3. Chạy bridge đồng bộ nếu có cổng Native đang hoạt động
    if active_native_conn and active_native_port:
        run_live_sync_loop(active_native_port, active_native_conn, docker_conn)
    else:
        print("  ✅ Không cần đồng bộ nếu camera đã kết nối trực tiếp vào Docker cổng 5432.")


if __name__ == "__main__":
    main()
