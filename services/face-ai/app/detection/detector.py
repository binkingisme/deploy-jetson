"""Detection wrapper (FR-003).

Extracts face detections from DeepStream NvDsBatchMeta. The actual inference
runs in the DeepStream primary GIE; this module parses object metadata and
provides typed Detection objects.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class Detection:
    """A single detected face."""

    bbox: tuple[float, float, float, float]  # (left, top, width, height)
    confidence: float
    class_id: int
    frame_id: int
    obj_meta: Any = None  # NvDsObjectMeta (pyds) if available
    landmarks: np.ndarray | None = None  # (5, 2) facial keypoints (x, y)


class FaceDetector:
    """Parses DeepStream detection metadata into Detection objects.

    DeepStream probes call `on_meta` for each batch; this class filters to
    the configured class (face) and normalizes quads to bboxes.
    """

    def __init__(self, class_id: int = 0):
        self.class_id = class_id

    def parse_batch(self, batch_meta: Any) -> list[Detection]:
        """Parse all face detections from a NvDsBatchMeta."""
        detections: list[Detection] = []

        frame_meta = batch_meta.frame_meta_list
        while frame_meta is not None:
            fmeta = frame_meta.data
            if not fmeta:
                break

            frame_id = int(fmeta.frame_num)
            obj_meta = fmeta.obj_meta_list
            while obj_meta is not None:
                ometa = obj_meta.data
                if not ometa:
                    break
                if ometa.class_id == self.class_id:
                    rect = ometa.rect_params
                    bbox = (
                        float(rect.left),
                        float(rect.top),
                        float(rect.width),
                        float(rect.height),
                    )
                    detections.append(
                        Detection(
                            bbox=bbox,
                            confidence=float(rect.confidence),
                            class_id=int(ometa.class_id),
                            frame_id=frame_id,
                            obj_meta=ometa,
                        )
                    )
                obj_meta = obj_meta.next
            frame_meta = frame_meta.next

        return detections

    def crop_face(self, frame: np.ndarray, det: Detection) -> np.ndarray:
        """Crop a face region from a BGR frame."""
        left, top, width, height = det.bbox
        x0 = max(0, int(left))
        y0 = max(0, int(top))
        x1 = min(frame.shape[1], int(left + width))
        y1 = min(frame.shape[0], int(top + height))
        if x1 <= x0 or y1 <= y0:
            return np.empty((0, 0, 3), dtype=np.uint8)
        return frame[y0:y1, x0:x1]
