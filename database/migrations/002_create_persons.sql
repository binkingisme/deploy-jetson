-- ============================================================
-- Migration 002: persons
-- ============================================================
-- Spec Section 13.2

CREATE TABLE IF NOT EXISTS persons (
    person_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_code VARCHAR(100) UNIQUE,
    full_name    VARCHAR(255) NOT NULL,
    status       VARCHAR(30)  NOT NULL DEFAULT 'active',
    metadata     JSONB,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_persons_full_name ON persons (full_name);
CREATE INDEX IF NOT EXISTS idx_persons_status ON persons (status);
