-- ============================================================
-- Migration 006: identity_thresholds
-- ============================================================
-- Spec Section 13.6

CREATE TABLE IF NOT EXISTS identity_thresholds (
    threshold_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    threshold_table_version VARCHAR(100) NOT NULL,
    identity_id             UUID REFERENCES persons (person_id),
    threshold_type          VARCHAR(30) NOT NULL,
    threshold_value         REAL NOT NULL,
    fallback_used           BOOLEAN NOT NULL DEFAULT FALSE,
    n_impostor_scores       INTEGER,
    n_exceedances           INTEGER,
    u_quantile              REAL,
    u_value                 REAL,
    alpha                   REAL,
    gpd_shape               REAL,
    gpd_scale               REAL,
    fit_status              VARCHAR(20) NOT NULL,
    model_version           VARCHAR(100) NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_thresholds_identity ON identity_thresholds (identity_id);
CREATE INDEX IF NOT EXISTS idx_thresholds_version ON identity_thresholds (threshold_table_version);
