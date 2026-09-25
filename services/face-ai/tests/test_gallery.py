"""Unit tests for gallery manager (in-memory cosine search)."""
from __future__ import annotations

import numpy as np
import pytest

from app.gallery.manager import GalleryManager
from app.config.settings import GalleryConfig, PostgresConfig


class _FakeGallery(GalleryManager):
    """Gallery that bypasses DB by injecting an in-memory matrix."""

    def __init__(
        self,
        matrix: np.ndarray,
        ids: list[str],
        names: list[str],
        keys: list[str] | None = None,
    ):
        super().__init__(PostgresConfig(), GalleryConfig())
        self.embedding_matrix = matrix
        self.person_ids = ids
        self.person_names = names
        self.identity_keys = keys or ids
        self.n_vectors = len(ids)
        self.n_persons = len(set(ids))
        self._loaded = True


@pytest.fixture
def gallery() -> _FakeGallery:
    rng = np.random.default_rng(0)
    emb = rng.normal(size=(4, 512)).astype(np.float32)
    emb = emb / np.linalg.norm(emb, axis=1, keepdims=True)
    return _FakeGallery(
        emb, ["p1", "p2", "p3", "p4"], ["A", "B", "C", "D"]
    )


def test_search_returns_closest(gallery: _FakeGallery) -> None:
    query = gallery.embedding_matrix[2]
    res = gallery.search(query, top_k=1)
    assert len(res) == 1
    assert res[0].person_id == "p3"
    assert res[0].similarity > 0.99


def test_zero_vector_not_loaded() -> None:
    pass
