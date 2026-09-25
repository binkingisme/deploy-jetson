"""Verify which gallery embeddings are wrong by re-embedding source captures.

Reads the already-available capture images (e.g. Nam / Phuc) on this machine,
computes their embeddings with the same model, and reports the cosine
similarity of each capture against every DB gallery identity.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "services" / "face-ai"))

from app.config.settings import RecognitionConfig  # noqa: E402
from app.recognition.embedder import FaceEmbedder  # noqa: E402


def load_env_file(env_path: Path) -> None:
    import os

    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip("'\""))


def main() -> int:
    paths = sys.argv[1:]
    if not paths:
        print("usage: verify_captures.py <img1> [img2] ...")
        return 2

    load_env_file(_ROOT / ".env")
    from app.config.settings import load_settings

    pg = load_settings([_ROOT / "configs" / "app.yaml"]).postgresql

    rec_cfg = RecognitionConfig()  # runtime: tensorrt on Jetson
    embedder = FaceEmbedder(rec_cfg)

    import cv2
    import psycopg2

    conn = psycopg2.connect(pg.dsn)
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
            rows = cur.fetchall()
    finally:
        conn.close()

    db: dict[str, np.ndarray] = {}
    for code, name, emb in rows:
        e = np.frombuffer(bytes(emb), dtype=np.float32)
        e = e / (np.linalg.norm(e) + 1e-12)
        db[code or name or ""] = e

    gallery_keys = sorted(db)
    print(f"[verify] gallery = {len(gallery_keys)} identities")

    for p in paths:
        img = cv2.imread(p)
        if img is None:
            print(f"[verify] cannot read {p}")
            continue
        res = embedder.extract(img)
        if res is None:
            print(f"[verify] no face/embedding in {p}")
            continue
        q = res.embedding / (np.linalg.norm(res.embedding) + 1e-12)
        sims = {k: float(np.dot(q, db[k])) for k in gallery_keys}
        top = sorted(sims.items(), key=lambda x: -x[1])[:8]
        print(f"\n[verify] {p} -> top-8:")
        for k, s in top:
            print(f"    {k:<16} {s:.3f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())