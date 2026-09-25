"""Face tracking state machine (FR-005, Section 14, "states").

Tracks a face across frames, keeps a stable track_id, and moves through
lifecycle states: NEW -> OBSERVING -> RECOGNIZING -> KNOWN/UNKNOWN -> LOST.

Association is greedy IoU matching between detections and active tracks.
This runs in Python because the primary GIE uses tensor-meta output (no
parsed object meta), so a DeepStream object-level tracker cannot be used.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import time


class TrackState(Enum):
    """Lifecycle states of a tracked face."""

    NEW = "new"
    OBSERVING = "observing"
    RECOGNIZING = "recognizing"
    KNOWN = "known"
    UNKNOWN = "unknown"
    LOST = "lost"


def _iou(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    """IoU of two (left, top, width, height) boxes."""
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    xx1 = max(ax1, bx1)
    yy1 = max(ay1, by1)
    xx2 = min(ax2, bx2)
    yy2 = min(ay2, by2)
    inter = max(0.0, xx2 - xx1) * max(0.0, yy2 - yy1)
    area_a = max(0.0, aw) * max(0.0, ah)
    area_b = max(0.0, bw) * max(0.0, bh)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


@dataclass
class Track:
    """A single tracked face."""

    track_id: int
    state: TrackState = TrackState.NEW
    bbox: tuple[float, float, float, float] | None = None
    best_embedding: object | None = None  # np.ndarray placeholder
    best_similarity: float = 0.0
    created_at: float = field(default_factory=time)
    last_seen: float = field(default_factory=time)
    quality_ok_count: int = 0
    recognized: bool = False
    # Temporal voting: latest decision per observation (person_name|None, sim, thr)
    votes: list[tuple[str | None, float, float]] = field(default_factory=list)
    re_eval: bool = False  # True while re-evaluating an UNKNOWN track


class FaceTracker:
    """Owns the lifecycle of active tracks via greedy IoU association."""

    def __init__(
        self,
        observe_frames: int = 3,
        track_timeout_s: float = 3.0,
        iou_threshold: float = 0.4,
    ):
        self.observe_frames = observe_frames
        self.track_timeout_s = track_timeout_s
        self.iou_threshold = iou_threshold
        self.tracks: dict[int, Track] = {}
        self._next_id = 1

    def new_track(self) -> Track:
        """Register a NEW track."""
        track = Track(track_id=self._next_id)
        self._next_id += 1
        self.tracks[track.track_id] = track
        return track

    def associate(
        self,
        bboxes: list[tuple[float, float, float, float]],
    ) -> list[tuple[Track, tuple[float, float, float, float]]]:
        """Greedy IoU association of detections to active tracks.

        Returns one ``(track, bbox)`` pair per detection: matched tracks are
        updated in place; unmatched detections start NEW tracks.
        """
        now = time()
        active = list(self.tracks.values())

        pairs: list[tuple[Track, tuple[float, float, float, float]]] = []
        used_tracks: set[int] = set()
        used_dets: set[int] = set()

        for di, bbox in enumerate(bboxes):
            best_track: Track | None = None
            best_iou = self.iou_threshold
            for track in active:
                if track.track_id in used_tracks or track.bbox is None:
                    continue
                iou = _iou(track.bbox, bbox)
                if iou >= best_iou:
                    best_track = track
                    best_iou = iou
            if best_track is not None:
                best_track.bbox = bbox
                best_track.last_seen = now
                used_tracks.add(best_track.track_id)
                if best_track.state == TrackState.NEW:
                    best_track.quality_ok_count += 1
                    if best_track.quality_ok_count >= self.observe_frames:
                        best_track.state = TrackState.OBSERVING
                pairs.append((best_track, bbox))
                used_dets.add(di)

        for di, bbox in enumerate(bboxes):
            if di in used_dets:
                continue
            track = self.new_track()
            track.bbox = bbox
            track.last_seen = now
            track.quality_ok_count = 1
            pairs.append((track, bbox))

        return pairs

    def update(self, bbox: tuple[float, float, float, float]) -> Track:
        """Compatibility wrapper: associate a single bbox and return its track."""
        pairs = self.associate([bbox])
        if not pairs:
            return self.new_track()
        track = pairs[0][0]
        return track

    def expire(self, now: float | None = None) -> list[Track]:
        """Mark tracks as LOST after timeout, return the lost ones."""
        now = now or time()
        lost: list[Track] = []
        for track_id in list(self.tracks):
            track = self.tracks[track_id]
            if now - track.last_seen > self.track_timeout_s:
                track.state = TrackState.LOST
                lost.append(track)
                del self.tracks[track_id]
        return lost

    def active(self) -> list[Track]:
        """Return currently active (non-final) tracks."""
        return [
            t
            for t in self.tracks.values()
            if t.state not in (TrackState.KNOWN, TrackState.UNKNOWN, TrackState.LOST)
        ]
