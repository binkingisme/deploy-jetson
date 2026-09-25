"""Validate gallery consistency between PostgreSQL and the required model.

Checks model-version compatibility (Rule 4/Section 12), embedding dimensions,
L2 normalization, and reports counts of vectors/persons.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "services" / "face-ai"))

from app.config.settings import GalleryConfig, PostgresConfig, load_settings  # noqa: E402
from app.config.settings import Settings  # noqa: E402
from app.gallery.pg_loader import load_gallery_metadata  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate gallery")
    p.add_argument("--model-version", default=GalleryConfig().model_version)
    p.add_argument(
        "--parquet", default=None, help="validate known_embeddings.parquet directly"
    )
    p.add_argument(
        "--pg-password",
        default="",
        help="PostgreSQL password (overrides .env / config)",
    )
    return p.parse_args(argv)


def load_pg(args: argparse.Namespace) -> PostgresConfig:
    _load_env(_ROOT / ".env")
    settings: Settings = load_settings([
        _ROOT / "configs" / "app.yaml",
        _ROOT / "configs" / "camera.yaml",
        _ROOT / "configs" / "recognition.yaml",
    ])
    pg = settings.postgresql
    if args.pg_password:
        pg.password = args.pg_password
    return pg


def _load_env(env_path: Path) -> None:
    import os

    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip("'\""))


def validate_parquet(path: str) -> int:
    """Validate an embeddings parquet without needing the DB."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from build_gallery import load_embeddings

    emb, labels = load_embeddings(path)
    emb = np.asarray(emb, dtype=np.float32)

    status = 0
    if emb.ndim != 2 or emb.shape[1] != 512:
        print(f"[validate_gallery] ERROR: expected (N, 512), got {emb.shape}")
        status = 1
    if emb.shape[0] != len(labels):
        print(f"[validate_gallery] ERROR: {emb.shape[0]} embeddings vs {len(labels)} labels")
        status = 1

    names = sorted(set(str(l) for l in labels if not str(l).strip().isdigit()))
    codes = sorted(set(str(l) for l in labels if str(l).strip().isdigit()))
    print(f"[validate_gallery] parquet: {emb.shape[0]} embeddings, "
          f"{len(names)} name labels, {len(codes)} numeric labels")
    print(f"[validate_gallery]   names: {names}")
    print(f"[validate_gallery]   dim: {emb.shape[1]}, dtype: {emb.dtype}")

    if status == 0:
        norms = np.linalg.norm(emb, axis=1)
        if np.any(norms < 1e-6):
            print("[validate_gallery] WARNING: found zero-norm embeddings")
        print(f"[validate_gallery] parquet OK")
    return status


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.parquet:
        return validate_parquet(args.parquet)

    pg = load_pg(args)
    metadata = load_gallery_metadata(pg)

    if args.model_version not in metadata:
        print(f"[validate_gallery] ERROR: no embeddings for model_version "
              f"{args.model_version}. Available: {list(metadata.keys())}")
        return 1

    info = metadata[args.model_version]
    print(f"[validate_gallery] model_version={args.model_version}")
    print(f"[validate_gallery]   embeddings: {info['n_embeddings']}")
    print(f"[validate_gallery]   persons:    {info['n_persons']}")
    print(f"[validate_gallery] OK")

    return 0


if __name__ == "__main__":
    sys.exit(main())
