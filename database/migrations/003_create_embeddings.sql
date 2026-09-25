-- ============================================================
-- Migration 003: face_embeddings
-- ============================================================
-- Spec Section 13.3

CREATE TABLE IF NOT EXISTS face_embeddings (
    embedding_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id           UUID NOT NULL REFERENCES persons(person_id) ON DELETE CASCADE,
    model_name          VARCHAR(100) NOT NULL,
    model_version       VARCHAR(100) NOT NULL,
    embedding_dimension INTEGER NOT NULL,
    embedding           BYTEA NOT NULL,
    quality_score       REAL,
    source_file         VARCHAR(255),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_embeddings_person FOREIGN KEY (person_id)
        REFERENCES persons (person_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_embeddings_person ON face_embeddings (person_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_model ON face_embeddings (model_version);
