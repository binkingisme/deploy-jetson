"""Recognition event generation (FR-012, Section 13.5).

Persists a recognition_events row on recognition outcomes (known/unknown,
with similarity, threshold, quality, snapshot path). Performs DB writes only
on decision events, never per-frame.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config.settings import PostgresConfig
from ..openset.decision import OpenSetDecision


@dataclass
class EventRecord:
    """Structured event to persist."""

    camera_id: str | None
    track_id: int
    decision: OpenSetDecision
    quality_score: float | None
    snapshot_path: str | None
    occurred_at: str  # ISO-8601


class EventGenerator:
    """Generates and persists recognition events to PostgreSQL."""

    def __init__(self, pg: PostgresConfig):
        self.pg = pg


    @staticmethod
    def _resolve_camera_uuid(cur, camera_id: str | None):
        """Map camera code ('camera_01') to the cameras table UUID."""
        if not camera_id:
            return None
        cur.execute(
            "SELECT camera_id FROM cameras WHERE camera_code = %s",
            (camera_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def persist(self, record: EventRecord) -> None:
        """Insert a single recognition event row."""
        import psycopg2

        decision = record.decision
        conn = psycopg2.connect(self.pg.dsn)
        try:
            with conn.cursor() as cur:
                camera_uuid = self._resolve_camera_uuid(cur, record.camera_id)
                cur.execute(
                    """
                    INSERT INTO recognition_events
                        (camera_id, track_id, person_id, status,
                         similarity, threshold_value, threshold_type,
                         fallback_used, quality_score, model_version,
                         occurred_at, snapshot_path)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        camera_uuid,
                        record.track_id,
                        decision.person_id,
                        "KNOWN" if decision.is_known else "UNKNOWN",
                        decision.similarity,
                        decision.threshold,
                        decision.threshold_type,
                        decision.fallback_used,
                        record.quality_score,
                        None,  # model_version set by caller if available
                        record.occurred_at,
                        record.snapshot_path,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
