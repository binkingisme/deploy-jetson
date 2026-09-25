#!/usr/bin/env python3
"""Self-test for the Jetson deployment (run ON the Jetson).

Verifies the deploy is complete and consistent:
  1. GPU / TensorRT / DeepStream availability
  2. TensorRT engine files (built by scripts/model/build_engines.sh)
  3. Python dependencies
  4. PostgreSQL connectivity + schema
  5. Embedding gallery (parquet) sanity
  6. Config file consistency (engine names match configs)

Usage:
    python3 scripts/setup/self_test_jetson.py
    python3 scripts/setup/self_test_jetson.py --verbose
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"
_results: list[tuple[str, str, str]] = []  # (name, status, detail)


def record(name: str, status: str, detail: str = "") -> None:
    _results.append((name, status, detail))


def run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


def check_gpu() -> None:
    rc, out = run(["nvidia-smi", "--query-gpu=count,name,memory.total", "--format=csv"])
    if rc == 0:
        record("GPU", PASS, out.replace("\n", "; "))
    else:
        record("GPU", WARN, "nvidia-smi not available (may be normal on some Jetson images)")


def find_trtexec() -> str | None:
    """trtexec is often installed by JetPack but not symlinked into PATH."""
    for cand in [
        shutil.which("trtexec"),
        "/usr/src/tensorrt/bin/trtexec",
        "/opt/nvidia/tensorrt/bin/trtexec",
        "/opt/TensorRT/bin/trtexec",
        "/usr/local/bin/trtexec",
    ]:
        if cand and Path(cand).is_file() and os.access(cand, os.X_OK):
            return cand
    return None


def check_trt() -> None:
    found = find_trtexec()
    if found:
        rc, out = run([found, "--version"])
        detail = (out.splitlines() or ["?"])[0] if rc == 0 else found
        record("TensorRT", PASS, f"{found} | {detail[:100]}")
    else:
        detail = (
            "missing. Check /usr/src/tensorrt/bin/trtexec or run "
            "sudo apt-get install -y tensorrt"
        )
        record("TensorRT", FAIL, detail)


def check_deepstream() -> None:
    if Path("/opt/nvidia/deepstream/deepstream").is_dir():
        record("DeepStream", PASS, "/opt/nvidia/deepstream/deepstream exists")
        return
    rc, _ = run(["deepstream-app", "--version"])
    if rc == 0:
        record("DeepStream", PASS, "deepstream-app found")
    else:
        record("DeepStream", WARN, "not found (pipeline may not run)")


def check_engines() -> None:
    required = {
        "detector": "models/detector/det_10g_fp16.engine",
        "recognition": "models/recognition/face_recog_fp16.engine",
    }
    for name, rel in required.items():
        p = ROOT / rel
        if p.is_file() and p.stat().st_size > 0:
            record(f"engine:{name}", PASS, f"{rel} ({p.stat().st_size:,} bytes)")
        else:
            record(f"engine:{name}", FAIL, f"missing {rel} - run scripts/model/build_engines.sh")


def check_python_deps() -> None:
    for mod in ["numpy", "psycopg2", "pyarrow", "yaml", "cv2"]:
        try:
            __import__(mod)
            record(f"pydep:{mod}", PASS)
        except ImportError:
            record(f"pydep:{mod}", FAIL, f"pip install {mod}")


def load_env() -> dict[str, str]:
    """Minimal .env reader (no python-dotenv dependency)."""
    env: dict[str, str] = {}
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return env
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip().strip("'\"")
    return env


def check_postgres() -> None:
    try:
        import psycopg2
    except ImportError:
        record("PostgreSQL", FAIL, "psycopg2 not installed")
        return

    env = load_env()
    cfg = {
        "host": env.get("POSTGRES_HOST", "localhost"),
        "port": int(env.get("POSTGRES_PORT", "5432")),
        "dbname": env.get("POSTGRES_DB", "open_set_fr"),
        "user": env.get("POSTGRES_USER", "open_set_fr"),
        "password": env.get("POSTGRES_PASSWORD", "open_set_fr_secret"),
    }
    host = socket.gethostbyname(cfg["host"] if cfg["host"] != "localhost" else "localhost")
    try:
        conn = psycopg2.connect(
            host=host, port=cfg["port"], dbname=cfg["dbname"],
            user=cfg["user"], password=cfg["password"],
            connect_timeout=5,
        )
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
            n_tables = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM public.persons")
            n_persons = cur.fetchone()[0]
        conn.close()
        record("PostgreSQL", PASS, f"connected ({cfg['user']}@{cfg['dbname']}), {n_tables} tables, {n_persons} persons")
    except Exception as e:  # noqa: BLE001
        record(
            "PostgreSQL",
            FAIL,
            f"cannot connect: {str(e)[:160]} (check .env POSTGRES_PASSWORD)",
        )


def check_parquet() -> None:
    candidates = [
        ROOT / "known_embeddings.parquet",
        ROOT / "jetson_deploy_v2" / "known_embeddings.parquet",
    ]
    found = next((p for p in candidates if p.is_file()), None)
    if not found:
        record("parquet", WARN, "not found (expected at known_embeddings.parquet)")
        return
    try:
        import pyarrow.parquet as pq
        import numpy as np

        table = pq.read_table(str(found))
        embs = table.column("embedding").to_pylist()
        e = np.frombuffer(embs[0], dtype=np.float32)
        dim_ok = e.shape[0] == 512
        record(
            "parquet",
            PASS if dim_ok else FAIL,
            f"{found.name}: {table.num_rows} rows, dim={e.shape[0]}",
        )
    except Exception as e:  # noqa: BLE001
        record("parquet", FAIL, str(e)[:120])


def check_threshold_table() -> None:
    p = ROOT / "thresholds" / "threshold_table.json"
    if not p.is_file():
        record("thresholds", WARN, f"missing {p}")
        return
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        n_ids = len(data.get("identities", []))
        has_global = "global_evt" in data
        if n_ids > 0:
            record("thresholds", PASS, f"{n_ids} identities, global={has_global}")
        else:
            record(
                "thresholds",
                WARN,
                f"placeholder file (0 identities) - copy the real "
                f"threshold_table.json (see docs/DEPLOY_JETSON.md)",
            )
    except Exception as e:  # noqa: BLE001
        record("thresholds", FAIL, str(e)[:120])


def check_config_consistency() -> None:
    ds_dir = ROOT / "configs" / "deepstream"
    scripts_map = {
        "det_10g_fp16.engine": "configs/deepstream/config_infer_primary.txt",
        "face_recog_fp16.engine": "configs/deepstream/config_infer_secondary.txt",
    }
    for engine_name, cfg_rel in scripts_map.items():
        cfg = ds_dir / Path(cfg_rel).name
        if not cfg.is_file():
            record(f"cfg:{cfg_rel}", FAIL, "config file missing")
            continue
        text = cfg.read_text(encoding="utf-8", errors="ignore")
        if engine_name in text:
            record(f"cfg:{Path(cfg_rel).name}", PASS, f"references {engine_name}")
        else:
            record(f"cfg:{Path(cfg_rel).name}", FAIL, f"does NOT reference {engine_name}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Jetson deploy self-test")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    print("=" * 62)
    print(f" Self-test: {ROOT.name}   (run on the Jetson)")
    print("=" * 62)

    check_gpu()
    check_trt()
    check_deepstream()
    check_engines()
    check_python_deps()
    check_postgres()
    check_parquet()
    check_threshold_table()
    check_config_consistency()

    n_pass = sum(1 for _, s, _ in _results if s == PASS)
    n_fail = sum(1 for _, s, _ in _results if s == FAIL)
    n_warn = sum(1 for _, s, _ in _results if s == WARN)

    print()
    print(f"{'CHECK':<22} {'STATUS':<6} DETAIL")
    print("-" * 62)
    for name, status, detail in _results:
        print(f"{name:<22} [{status}]{' ' if len(status)==4 else ''} {detail}")
        if args.verbose and status != PASS and detail:
            pass

    print("-" * 62)
    print(f"TOTAL: {n_pass} PASS / {n_fail} FAIL / {n_warn} WARN")

    if n_fail:
        print("\n> Fix FAIL items above, then re-run.")
        return 1
    if n_warn and not args.verbose:
        print("\n> There are WARN items. Use --verbose for hints.")
    return 0


if __name__ == "__main__":
    sys.exit(main())