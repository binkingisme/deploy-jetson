"""Enroll a person into the PostgreSQL gallery.

Computes embeddings from provided face images via the same InsightFace model
used for runtime, then inserts them into face_embeddings.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "services" / "face-ai"))

from app.config.settings import PostgresConfig, RecognitionConfig  # noqa: E402
from app.recognition.embedder import FaceEmbedder  # noqa: E402
from app.gallery.pg_loader import insert_embeddings, upsert_person  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Enroll a person")
    p.add_argument("--student-code", required=True)
    p.add_argument("--full-name", required=True)
    p.add_argument("--images", nargs="+", required=True, help="face image paths")
    p.add_argument("--model-path", default="models/recognition/w600k_r50.onnx")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    pg = PostgresConfig()
    rec_cfg = RecognitionConfig(model_path=args.model_path)
    embedder = FaceEmbedder(rec_cfg)

    embeddings: list[np.ndarray] = []
    for img_path in args.images:
        import cv2

        img = cv2.imread(img_path)
        if img is None:
            print(f"[enroll] ERROR: cannot read {img_path}")
            continue
        result = embedder.extract(img)
        if result is None:
            print(f"[enroll] WARNING: zero embedding for {img_path}")
            continue
        embeddings.append(result.embedding)

    if not embeddings:
        print("[enroll] ERROR: no valid embeddings produced")
        return 1

    matrix = np.array(embeddings, dtype=np.float32)

    person_id = upsert_person(
        pg, identity_key=args.student_code, full_name=args.full_name
    )
    inserted = insert_embeddings(
        pg,
        person_id=person_id,
        model_name=rec_cfg.model_name,
        model_version=rec_cfg.model_version,
        embeddings=matrix,
    )
    print(f"[enroll] inserted {inserted} embeddings for {args.full_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
