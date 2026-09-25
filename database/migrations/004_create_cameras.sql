-- ============================================================
-- Migration 004: cameras
-- ============================================================
-- Spec Section 13.4

CREATE TABLE IF NOT EXISTS cameras (
    camera_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_code   VARCHAR(100) UNIQUE NOT NULL,
    name          VARCHAR(255) NOT NULL,
    source_type   VARCHAR(30)  NOT NULL,
    source_config JSONB NOT NULL,
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
