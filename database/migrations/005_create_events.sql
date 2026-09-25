-- ============================================================
-- Migration 005: recognition_events
-- ============================================================
-- Spec Section 13.5

CREATE TABLE IF NOT EXISTS recognition_events (
    event_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id               UUID REFERENCES cameras (camera_id),
    track_id                BIGINT NOT NULL,
    person_id               UUID REFERENCES persons (person_id),
    status                  VARCHAR(30) NOT NULL,
    similarity              REAL,
    threshold_value         REAL,
    threshold_type          VARCHAR(30) NOT NULL,
    fallback_used           BOOLEAN NOT NULL DEFAULT FALSE,
    quality_score           REAL,
    model_version           VARCHAR(100),
    threshold_table_version VARCHAR(100),
    error_code              VARCHAR(60),
    occurred_at             TIMESTAMPTZ NOT NULL,
    snapshot_path           TEXT,
    metadata                JSONB
);

CREATE INDEX IF NOT EXISTS idx_events_occurred_at ON recognition_events (occurred_at);
CREATE INDEX IF NOT EXISTS idx_events_person ON recognition_events (person_id);
CREATE INDEX IF NOT EXISTS idx_events_camera ON recognition_events (camera_id);
CREATE INDEX IF NOT EXISTS idx_events_status ON recognition_events (status);
CREATE INDEX IF NOT EXISTS idx_events_track ON recognition_events (track_id);
