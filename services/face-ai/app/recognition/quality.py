"""Face quality evaluation (FR-004 quality gate).

Evaluates whether a detected face crop is good enough to embed/recognize.
Rejects excessively blurry, tiny, or over-/under-exposed crops.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config.settings import QualityConfig


@dataclass
class FaceQuality:
    """Result of quality evaluation for one face."""

    blur: float
    brightness: float
    face_size: int
    detection_conf: float
    is_low_quality: bool


class FaceQualityEvaluator:
    """Computes quality metrics and rejects bad crops."""

    def __init__(self, config: QualityConfig):
        self.config = config

    def evaluate(
        self, face_bgr: np.ndarray, detection_conf: float
    ) -> FaceQuality:
        """Evaluate a face crop and flag low-quality faces."""
        import cv2

        if face_bgr.ndim != 3 or face_bgr.size == 0:
            return FaceQuality(
                blur=0.0,
                brightness=0.0,
                face_size=0,
                detection_conf=detection_conf,
                is_low_quality=True,
            )

        gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
        blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        brightness = float(np.mean(face_bgr))
        face_size = max(face_bgr.shape[:2])

        low = False
        if detection_conf < self.config.min_confidence:
            low = True
        if face_size < self.config.min_face_size:
            low = True
        if blur < self.config.max_blur:
            low = True
        if brightness < self.config.min_brightness:
            low = True
        if brightness > self.config.max_brightness:
            low = True

        return FaceQuality(
            blur=blur,
            brightness=brightness,
            face_size=face_size,
            detection_conf=detection_conf,
            is_low_quality=low,
        )
