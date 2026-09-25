"""Unit tests for face embedder / quality."""
from __future__ import annotations

import numpy as np
import pytest

from app.recognition.embedder import FaceEmbedder
from app.recognition.quality import FaceQualityEvaluator
from app.config.settings import QualityConfig, RecognitionConfig


@pytest.fixture
def dummy_face() -> np.ndarray:
    """Return a plain gray BGR face-sized image."""
    return np.full((112, 112, 3), 128, dtype=np.uint8)


def test_quality_rejects_tiny_face(dummy_face: np.ndarray) -> None:
    evaluator = FaceQualityEvaluator(QualityConfig(min_face_size=40))
    small = dummy_face[::4, ::4]  # shrink to 28x28
    q = evaluator.evaluate(small, detection_conf=0.9)
    assert q.is_low_quality is True


def test_quality_accepts_good_face() -> None:
    evaluator = FaceQualityEvaluator(QualityConfig())
    rng = np.random.default_rng(1)
    textured = rng.integers(60, 200, size=(112, 112, 3), dtype=np.uint8)
    q = evaluator.evaluate(textured, detection_conf=0.9)
    assert q.is_low_quality is False


def test_preprocess_shape() -> None:
    embedder = FaceEmbedder(
        RecognitionConfig(input_size=[112, 112], runtime="onnx")
    )
    img = np.zeros((200, 150, 3), dtype=np.uint8)
    tensor = embedder.preprocess(img)
    assert tensor.shape == (1, 3, 112, 112)
