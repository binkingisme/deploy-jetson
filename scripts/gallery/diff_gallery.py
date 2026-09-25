"""Compare a known_embeddings parquet/npz against the PostgreSQL gallery.

For every label in the source file, loads the current DB embeddings (any
model_version) and reports:
  - labels in source but missing in DB
  - labels in DB but missing in source
  - max cosine distance per shared label (0 => identical)

Read-only; does not modify the database.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "services" / "face-ai"))

from app.config.settings import load_settings  # noqa: E402


def load_source(path: str) -> tuple[np.ndarray, list[str]]:
    suffix = Path(path).suffix.lower()
    if suffix == ".parquet":
        import pyarrow.parquet as pq

        table = pq.read_table(path)
        labels = [str(x) for x in table.column("label").to_pylist()]
        embs = [
            np.frombuffer(item, dtype=np.float32)
            for item in table.column("embedding").to_pylist()
        ]
        return np.asarray(embs, dtype=np.float32), labels
    if suffix == ".npz":
        data = np.load(path, allow_pickle=True)
        return data["embeddings"], [str(x) for x in data["labels"].tolist()]
    raise SystemExit(f"Unsupported format: {suffix}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    args = p.parse_args(argv)

    load_settings([_ROOT / "configs" / "app.yaml"])
    import psycopg2

    conn = psycopg2.connect(
        host="localhost", dbname="open_set_fr",
        user="open_set_fr", password="Nckh@2026",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.student_code, p.full_name, fe.embedding
                FROM face_embeddings fe
                JOIN persons p ON p.person_id = fe.person_id
                WHERE p.status = 'active'
                ORDER BY p.full_name
                """
            )
            db_rows = cur.fetchall()
    finally:
        conn.close()

    source_embs, src_labels = load_source(args.input)

    db: dict[str, list[np.ndarray]] = {}
    for code, name, emb in db_rows:
        key = code or name or ""
        db.setdefault(key, []).append(np.frombuffer(bytes(emb), dtype=np.float32))

    src_unique = list(dict.fromkeys(src_labels))
    db_keys = set(db)

    print(f"[diff] source: {len(src_labels)} embeddings / {len(src_unique)} labels")
    print(f"[diff] db    : {len(db)} labels")

    missing_in_db = [l for l in src_unique if l not in db_keys]
    missing_in_src = sorted(db_keys - set(src_unique))
    if missing_in_db:
        print(f"[diff] IN SOURCE, NOT IN DB: {missing_in_db}")
    if missing_in_src:
        print(f"[diff] IN DB, NOT IN SOURCE: {missing_in_src}")

    print("[diff] per-label max cosine distance (0.0 == identical):")
    n_changed = 0
    for label in src_unique:
        if label not in db:
            continue
        src = np.mean([e for e, l in zip(source_embs, src_labels) if l == label], axis=0)
        dbm = np.mean(np.array(db[label]), axis=0)
        src = src / (np.linalg.norm(src) + 1e-12)
        dbm = dbm / (np.linalg.norm(dbm) + 1e-12)
        dist = float(1.0 - float(np.dot(src, dbm)))
        if dist > 1e-4:
            n_changed += 1
        print(f"    {label:<12} {dist:.6f}")

    print(f"[diff] labels with changed embedding: {n_changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())