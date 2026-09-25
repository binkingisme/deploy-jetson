"""Replace the PostgreSQL gallery from a known_embeddings source.

Deletes all existing rows in face_embeddings for the target model_version
(and active persons), then re-imports embeddings from a parquet/npz file.

This is a destructive replace. It mirrors build_gallery.py label handling:
  - numeric label  -> persons.student_code
  - non-numeric    -> persons.full_name

Orphan persons without embeddings for the model_version are left in place
(only embeddings are purged), consistently with build_gallery semantics of
upserting persons and inserting embeddings.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "services" / "face-ai"))

from app.config.settings import GalleryConfig, load_settings  # noqa: E402
from app.gallery.pg_loader import insert_embeddings, upsert_person  # noqa: E402


def load_embeddings(path: str) -> tuple[np.ndarray, list[str]]:
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


def load_env_file(env_path: Path) -> None:
    """Load .env into os.environ (no python-dotenv dependency)."""
    import os

    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip("'\""))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Replace gallery embeddings")
    p.add_argument("--input", required=True)
    p.add_argument("--model-version", default=GalleryConfig().model_version)
    p.add_argument("--yes", action="store_true", help="skip confirmation")
    args = p.parse_args(argv)

    embeddings, labels = load_embeddings(args.input)
    labels = [str(l) for l in labels]
    print(
        f"[replace] loaded {embeddings.shape[0]} embeddings from {args.input} "
        f"for model_version={args.model_version}"
    )

    if not args.yes:
        answer = input(
            "[replace] DANGER: this deletes ALL existing gallery embeddings "
            f"for {args.model_version} and replaces them. Continue? [y/N] "
        )
        if answer.strip().lower() != "y":
            print("[replace] aborted")
            return 1

    load_env_file(_ROOT / ".env")
    settings = load_settings([_ROOT / "configs" / "app.yaml"])
    pg = settings.postgresql
    import psycopg2

    conn = psycopg2.connect(pg.dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM face_embeddings WHERE model_version = %s",
                (args.model_version,),
            )
            deleted = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    print(f"[replace] deleted {deleted} old embeddings")
    unique_labels = list(dict.fromkeys(labels))
    total = 0
    for label in unique_labels:
        mask = np.array(labels) == label
        person_embs = embeddings[mask]
        is_numeric = label.strip().isdigit()
        full_name = None if is_numeric else label
        person_id = upsert_person(pg, identity_key=label, full_name=full_name)
        inserted = insert_embeddings(
            pg,
            person_id=person_id,
            model_name="w600k_r50",
            model_version=args.model_version,
            embeddings=person_embs,
        )
        total += inserted
        print(
            f"[replace]   {label:<20} "
            f"{'[code]' if is_numeric else '[name]'}: {inserted} embeddings"
        )

    print(f"[replace] done. {total} embeddings across {len(unique_labels)} persons")
    return 0


if __name__ == "__main__":
    sys.exit(main())