"""Build/import the gallery into PostgreSQL from known_embeddings.

Source: `known_embeddings.parquet` (preferred, replaces the legacy `.faiss`)
or `known_embeddings.npz`.

Parquet schema:
    embedding: binary  (2048 bytes = 512 x float32)
    label:     string  (numeric code like "3137841" OR a name like "Binh")
    angle:     string  (yaw/pitch/roll placeholder, may be empty)

Label handling:
  - Numeric label  -> persons.student_code, full_name may come from a name
                      map (--names) or stays NULL
  - Non-numeric    -> persons.full_name (a real person name)

Each label becomes a distinct person; all its embeddings are inserted into
face_embeddings tied to that person's UUID.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "services" / "face-ai"))

from app.config.settings import GalleryConfig, PostgresConfig, load_settings  # noqa: E402
from app.gallery.pg_loader import insert_embeddings, upsert_person  # noqa: E402


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


class GalleryBuildError(Exception):
    """Raised on invalid gallery artifacts."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Import known_embeddings.parquet/npz into PostgreSQL"
    )
    p.add_argument(
        "--input",
        dest="input_path",
        default="jetson_deploy_v2/known_embeddings.parquet",
        help="path to known_embeddings.parquet (or .npz fallback)",
    )
    p.add_argument(
        "--names",
        default={},
        help="JSON map of numeric label -> full name, e.g. '{\"3137841\":\"An\"}'",
    )
    p.add_argument("--model-name", default="w600k_r50")
    p.add_argument("--model-version", default=GalleryConfig().model_version)
    p.add_argument(
        "--pg-password",
        default="",
        help="PostgreSQL password (overrides .env / config)",
    )
    return p.parse_args(argv)


def load_embedding_parquet(path: str) -> tuple[np.ndarray, list[str]]:
    """Load (embeddings, labels) from a parquet file."""
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover
        raise GalleryBuildError(
            "pyarrow is required to read parquet; pip install pyarrow"
        ) from exc

    table = pq.read_table(path)
    labels = table.column("label").to_pylist()
    embs = [
        np.frombuffer(item, dtype=np.float32)
        for item in table.column("embedding").to_pylist()
    ]
    return np.asarray(embs, dtype=np.float32), labels


def load_embedding_npz(path: str) -> tuple[np.ndarray, list[str]]:
    """Load (embeddings, labels) from an NPZ file (legacy fallback)."""
    data = np.load(path, allow_pickle=True)
    if "embeddings" not in data.files or "labels" not in data.files:
        raise GalleryBuildError(
            f"NPZ must contain 'embeddings' and 'labels'; got {data.files}"
        )
    return data["embeddings"], data["labels"].tolist()


def load_embeddings(path: str) -> tuple[np.ndarray, list[str]]:
    """Dispatch by extension: parquet preferred, npz fallback."""
    suffix = Path(path).suffix.lower()
    if suffix == ".parquet":
        return load_embedding_parquet(path)
    if suffix == ".npz":
        return load_embedding_npz(path)
    raise GalleryBuildError(f"Unsupported gallery format: {suffix}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    embeddings, labels = load_embeddings(args.input_path)
    labels = [str(l) for l in labels]
    if embeddings.shape[1] != 512:
        print(f"[build_gallery] WARNING: expected 512-dim, got {embeddings.shape[1]}")
    unique_labels = list(dict.fromkeys(labels))

    names_map: dict[str, str] = {}
    if args.names:
        import json

        names_map = json.loads(args.names)

    print(
        f"[build_gallery] loaded {embeddings.shape[0]} embeddings, "
        f"{len(unique_labels)} unique labels from {args.input_path}"
    )

    load_env_file(_ROOT / ".env")
    settings = load_settings([
        _ROOT / "configs" / "app.yaml",
        _ROOT / "configs" / "camera.yaml",
        _ROOT / "configs" / "recognition.yaml",
    ])
    pg = settings.postgresql
    if args.pg_password:
        pg.password = args.pg_password
    total = 0

    for label in unique_labels:
        mask = np.array(labels) == label
        person_embs = embeddings[mask]

        is_numeric = label.strip().isdigit()
        full_name = names_map.get(label) if is_numeric else label
        person_id = upsert_person(pg, identity_key=label, full_name=full_name)
        inserted = insert_embeddings(
            pg,
            person_id=person_id,
            model_name=args.model_name,
            model_version=args.model_version,
            embeddings=person_embs,
        )
        total += inserted
        print(
            f"[build_gallery]   {label:<20} "
            f"{'[code]' if is_numeric else '[name]'}: {inserted} embeddings"
        )

    print(f"[build_gallery] done. {total} embeddings across {len(unique_labels)} persons")
    return 0


if __name__ == "__main__":
    sys.exit(main())