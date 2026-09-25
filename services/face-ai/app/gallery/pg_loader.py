"""PostgreSQL gallery loader helpers (FR-006, Section 13).

Low-level SQL operations for loading and mutating the embedding gallery.
Runtime gallery is kept in RAM (see manager.GalleryManager); this module is
used at startup and during enrollment/build operations.
"""
from __future__ import annotations

import json
from typing import Any

import numpy as np

from ..config.settings import PostgresConfig


class GalleryLoaderError(Exception):
    """Raised on PostgreSQL gallery operation failures."""


def upsert_person(
    pg: PostgresConfig,
    identity_key: str,
    full_name: str | None = None,
    metadata: Any = None,
) -> str:
    """Create (or return existing) person for a gallery label.

    `identity_key` is the label from known_embeddings.parquet / threshold
    table (numeric code like ``3137841`` or a name like ``Binh``). It maps to
    ``persons.student_code``; the returned value is the person ``UUID``.

    For non-numeric labels (a real name), the label is treated as the
    person's full name (and student_code is left empty).
    """
    import psycopg2

    is_numeric = identity_key.strip().isdigit()
    if full_name is None:
        # persons.full_name is NOT NULL; fall back to the label itself so
        # numeric codes (student IDs) still produce a valid name row.
        full_name = identity_key
    student_code = identity_key if is_numeric else None

    conn = psycopg2.connect(pg.dsn)
    try:
        with conn.cursor() as cur:
            if student_code is not None:
                cur.execute("SELECT person_id::text FROM persons WHERE student_code = %s", (student_code,))
                row = cur.fetchone()
                if row:
                    conn.commit()
                    return row[0]
            if not is_numeric:
                cur.execute("SELECT person_id::text FROM persons WHERE full_name = %s", (full_name,))
                row = cur.fetchone()
                if row:
                    conn.commit()
                    return row[0]

            cur.execute(
                """
                INSERT INTO persons (student_code, full_name, status, metadata)
                VALUES (%s, %s, 'active', %s::jsonb)
                RETURNING person_id::text
                """,
                (
                    student_code,
                    full_name,
                    json.dumps(metadata) if metadata is not None else None,
                ),
            )
            person_id = cur.fetchone()[0]
        conn.commit()
        return person_id
    finally:
        conn.close()


def load_gallery_metadata(pg: PostgresConfig) -> dict[str, Any]:
    """Return summary metadata about the stored gallery."""
    import psycopg2

    conn = psycopg2.connect(pg.dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT fe.model_version,
                       COUNT(*) AS n_embeddings,
                       COUNT(DISTINCT fe.person_id) AS n_persons
                FROM face_embeddings fe
                GROUP BY fe.model_version
                """
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return {
        model_version: {
            "n_embeddings": n_emb,
            "n_persons": n_people,
        }
        for model_version, n_emb, n_people in rows
    }


def insert_embeddings(
    pg: PostgresConfig,
    person_id: str,
    model_name: str,
    model_version: str,
    embeddings: np.ndarray,
    quality_scores: list[float] | None = None,
) -> int:
    """Insert one or more embeddings for a person. Returns count inserted."""
    import psycopg2

    if embeddings.ndim != 2:
        raise GalleryLoaderError("embeddings must be a 2D array (N, dim)")

    conn = psycopg2.connect(pg.dsn)
    inserted = 0
    try:
        with conn.cursor() as cur:
            for i, emb in enumerate(embeddings):
                emb = np.asarray(emb, dtype=np.float32)
                emb = emb / (np.linalg.norm(emb) + 1e-12)
                quality = quality_scores[i] if quality_scores else None
                cur.execute(
                    """
                    INSERT INTO face_embeddings
                        (person_id, model_name, model_version,
                         embedding_dimension, embedding, quality_score)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        person_id,
                        model_name,
                        model_version,
                        emb.shape[0],
                        emb.tobytes(),
                        quality,
                    ),
                )
                inserted += 1
        conn.commit()
    finally:
        conn.close()

    return inserted
