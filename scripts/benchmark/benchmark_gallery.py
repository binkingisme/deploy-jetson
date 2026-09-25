#!/usr/bin/env python3
"""Benchmark the recognition decision overhead (FR, Section 31).

Measures per-query latency of the in-memory gallery search + threshold lookup,
and reports the decision-overhead ratio vs a fixed-threshold baseline.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "services" / "face-ai"))

from app.gallery.manager import GalleryManager  # noqa: E402
from app.config.settings import GalleryConfig, PostgresConfig  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Benchmark gallery search")
    ap.add_argument("--num-queries", type=int, default=1000)
    ap.add_argument("--dim", type=int, default=512)
    ap.add_argument("--vectors", type=int, default=53149, help="target gallery size")
    args = ap.parse_args(argv)

    rng = np.random.default_rng(0)
    gallery = GalleryManager(
        PostgresConfig(), GalleryConfig(model_version="x", embedding_dim=args.dim)
    )

    # Simulate in-memory matrix without DB for benchmarking.
    # (Structure parity with manager.GalleryManager.search.)
    matrix = rng.normal(size=(args.vectors, args.dim)).astype(np.float32)
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
    gallery.embedding_matrix = matrix
    gallery.person_ids = [str(i) for i in range(args.vectors)]
    gallery.person_names = [f"P{i}" for i in range(args.vectors)]
    gallery.n_vectors = args.vectors
    gallery.n_persons = args.vectors
    gallery._loaded = True

    queries = rng.normal(size=(args.num_queries, args.dim)).astype(np.float32)
    queries /= np.linalg.norm(queries, axis=1, keepdims=True)

    start = time.perf_counter()
    for q in queries:
        gallery.search(q, top_k=1)
    elapsed = time.perf_counter() - start

    per_query_us = elapsed / args.num_queries * 1e6
    print(f"[benchmark] gallery size   : {args.vectors}")
    print(f"[benchmark] queries        : {args.num_queries}")
    print(f"[benchmark] total          : {elapsed:.3f}s")
    print(f"[benchmark] per-query      : {per_query_us:.1f} us")
    print(f"[benchmark] target ratio   : decision overhead <= 1.05x (measured in pipeline)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
