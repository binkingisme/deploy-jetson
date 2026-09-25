"""In-memory embedding gallery loaded from PostgreSQL.

Implements FR-006 decision premise: for a known identity, gallery search is
an exact in-memory cosine search (no DB per-frame, no FAISS required).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ..config.settings import GalleryConfig, PostgresConfig


class GalleryError(Exception):
    """Raised when gallery configuration/loading fails."""


@dataclass
class GalleryResult:
    """Single gallery match."""

    person_id: str          # persons.person_id (UUID)
    person_name: str        # persons.full_name
    identity_key: str       # persons.student_code or full-name label (threshold lookup key)
    similarity: float
    index: int


class GalleryManager:
    """In-memory gallery for runtime cosine search.

    Embeddings are loaded once at startup from PostgreSQL into a NumPy matrix.
    All runtime queries are pure matrix multiplications in RAM.
    Rule 4: no DB queries per frame.
    """

    def __init__(
        self, pg: PostgresConfig, gallery: GalleryConfig
    ):
        self.pg = pg
        self.gallery = gallery

        self.embedding_matrix: np.ndarray | None = None  # (N, 512) float32
        self.person_ids: list[str] = []
        self.person_names: list[str] = []
        self.identity_keys: list[str] = []
        self.n_vectors: int = 0
        self.n_persons: int = 0
        self._loaded = False

    def load(self) -> None:
        """Load all active embeddings for the configured model version."""
        import psycopg2

        conn = psycopg2.connect(self.pg.dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT p.person_id::text, p.full_name, p.student_code,
                           fe.embedding, fe.embedding_dimension
                    FROM face_embeddings fe
                    JOIN persons p ON p.person_id = fe.person_id
                    WHERE p.status = 'active'
                      AND fe.model_version = %s
                    """,
                    (self.gallery.model_version,),
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        if not rows:
            raise GalleryError(
                f"No embeddings found for model_version={self.gallery.model_version}"
            )

        dim = self.gallery.embedding_dim
        embeddings: list[np.ndarray] = []
        person_ids: list[str] = []
        person_names: list[str] = []
        identity_keys: list[str] = []

        for person_id, full_name, student_code, emb_bytes, emb_dim in rows:
            emb = np.frombuffer(bytes(emb_bytes), dtype=np.float32).copy()
            if emb.shape[0] != dim:
                continue
            emb = emb / (np.linalg.norm(emb) + 1e-12)  # ensure L2
            embeddings.append(emb)
            person_ids.append(person_id)
            person_names.append(full_name or person_id)
            identity_keys.append(student_code or full_name or person_id)

        self.embedding_matrix = np.array(embeddings, dtype=np.float32)
        self.person_ids = person_ids
        self.person_names = person_names
        self.identity_keys = identity_keys
        self.n_vectors = len(embeddings)
        self.n_persons = len(set(person_ids))
        self._loaded = True

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def search(
        self, query: np.ndarray, top_k: int = 1
    ) -> list[GalleryResult]:
        """Exact cosine search over the in-memory matrix."""
        if not self._loaded or self.embedding_matrix is None:
            return []

        scores = self.embedding_matrix @ query  # (N,) dot product on L2 norms

        if top_k == 1:
            best_idx = int(scores.argmax())
            return [
                GalleryResult(
                    person_id=self.person_ids[best_idx],
                    person_name=self.person_names[best_idx],
                    identity_key=self.identity_keys[best_idx],
                    similarity=float(scores[best_idx]),
                    index=best_idx,
                )
            ]

        top_n = min(top_k, scores.shape[0])
        top_indices = np.argpartition(scores, -top_n)[-top_n:]
        top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]
        return [
            GalleryResult(
                person_id=self.person_ids[i],
                person_name=self.person_names[i],
                identity_key=self.identity_keys[i],
                similarity=float(scores[i]),
                index=i,
            )
            for i in top_indices
        ]

    def reload(self) -> None:
        """Reload gallery from PostgreSQL."""
        self.load()
