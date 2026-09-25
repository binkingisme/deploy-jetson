"""Unit tests for open-set decision logic."""
from __future__ import annotations

import numpy as np
import pytest

from app.openset.decision import OpenSetRecognizer, ThresholdTable
from app.gallery.manager import GalleryManager
from app.config.settings import GalleryConfig, PostgresConfig


class _FakeGallery(GalleryManager):
    def __init__(self, sim: float, identity_key: str = "p1"):
        super().__init__(PostgresConfig(), GalleryConfig())
        self._sim = sim
        self._identity_key = identity_key
        self._loaded = True

    def search(self, query, top_k=1):
        result = type(
            "R",
            (),
            {
                "person_id": "p1",
                "person_name": "Alice",
                "identity_key": self._identity_key,
                "similarity": self._sim,
                "index": 0,
            },
        )
        return [result]


def _table(value: float | None, key: str = "p1") -> ThresholdTable:
    table = ThresholdTable()
    table._table = (
        {("identity_gpd", key): value} if value is not None else {}
    )
    return table


def test_fixed_decision_above_threshold() -> None:
    rec = OpenSetRecognizer(
        _FakeGallery(0.8), _table(None), GalleryConfig(), mode="fixed",
        fixed_threshold=0.5,
    )
    d = rec.decide(np.zeros(512, dtype=np.float32))
    assert d.is_known is True
    assert d.person_id == "p1"
    assert not d.fallback_used


def test_identity_gpd_below_threshold() -> None:
    rec = OpenSetRecognizer(
        _FakeGallery(0.3), _table(0.6), GalleryConfig(), mode="identity_gpd"
    )
    d = rec.decide(np.zeros(512, dtype=np.float32))
    assert d.is_known is False
    assert d.person_id is None


def test_identity_gpd_fallback_when_missing() -> None:
    rec = OpenSetRecognizer(
        _FakeGallery(0.8), _table(None), GalleryConfig(), mode="identity_gpd",
        fixed_threshold=0.5,
    )
    d = rec.decide(np.zeros(512, dtype=np.float32))
    assert d.is_known is True
    assert d.fallback_used is True


def test_identity_gpd_lookup_by_identity_key() -> None:
    rec = OpenSetRecognizer(
        _FakeGallery(0.55, identity_key="Binh"),
        _table(0.6, key="Binh"),
        GalleryConfig(),
        mode="identity_gpd",
    )
    d = rec.decide(np.zeros(512, dtype=np.float32))
    assert d.is_known is False
    assert d.threshold == 0.6


def test_global_evt_from_json_table() -> None:
    import json
    import tempfile

    payload = {
        "schema_version": "1.0",
        "global_evt": {
            "identity_id": "__global__",
            "threshold_type": "global_evt",
            "threshold_value": 0.45,
            "fixed_threshold": 0.5,
        },
        "identities": [
            {
                "identity_id": "3137841",
                "threshold_type": "identity_gpd",
                "threshold_value": 0.37,
                "fixed_threshold": 0.4,
            }
        ],
    }
    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(payload, f)
        path = f.name

    try:
        table = ThresholdTable()
        table.load_from_json(path)

        assert table.get("global_evt", "__global__") == 0.45
        assert table.get("identity_gpd", "3137841") == 0.37
        assert table.fallback("identity_gpd") == 0.4

        rec = OpenSetRecognizer(
            _FakeGallery(0.38, identity_key="3137841"),
            table,
            GalleryConfig(),
            mode="identity_gpd",
        )
        d = rec.decide(np.zeros(512, dtype=np.float32))
        assert d.is_known is True
        assert d.threshold == 0.37
    finally:
        import os

        os.unlink(path)
