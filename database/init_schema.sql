-- Initial Database Schema for Edge-based Open-Set Face Recognition
-- Compatible with PostgreSQL 13+ on NVIDIA Jetson

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'viewer',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed default Admin User (admin / admin)
INSERT INTO users (username, password_hash, role, is_active)
VALUES ('admin', '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', 'admin', true)
ON CONFLICT (username) DO NOTHING;

-- 2. Persons Table (Enrolled Identities)
CREATE TABLE IF NOT EXISTS persons (
    person_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_code VARCHAR(100) UNIQUE,
    full_name VARCHAR(255) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    created_by UUID REFERENCES users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Face Embeddings Table
CREATE TABLE IF NOT EXISTS face_embeddings (
    embedding_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    person_id UUID NOT NULL REFERENCES persons(person_id) ON DELETE CASCADE,
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(100) NOT NULL,
    embedding_dimension INTEGER NOT NULL,
    embedding BYTEA NOT NULL,
    quality_score REAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. Cameras Table
CREATE TABLE IF NOT EXISTS cameras (
    camera_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    camera_code VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    source_type VARCHAR(30) NOT NULL,
    source_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. Recognition Events Table
CREATE TABLE IF NOT EXISTS recognition_events (
    event_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    camera_id UUID REFERENCES cameras(camera_id) ON DELETE SET NULL,
    track_id BIGINT NOT NULL,
    person_id UUID REFERENCES persons(person_id) ON DELETE SET NULL,
    status VARCHAR(30) NOT NULL,           -- known / unknown / abstain / error
    similarity REAL,
    threshold_value REAL,
    threshold_type VARCHAR(30) NOT NULL,   -- fixed / global_evt / identity_gpd
    fallback_used BOOLEAN NOT NULL DEFAULT FALSE,
    quality_score REAL,
    model_version VARCHAR(100),
    threshold_table_version VARCHAR(100),
    error_code VARCHAR(60),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    snapshot_path TEXT,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- 6. Identity Thresholds Table (Offline EVT Audit & UI Table)
CREATE TABLE IF NOT EXISTS identity_thresholds (
    threshold_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    threshold_table_version VARCHAR(100) NOT NULL,
    identity_id UUID REFERENCES persons(person_id) ON DELETE SET NULL,
    threshold_type VARCHAR(30) NOT NULL,   -- identity_gpd / global_evt / fixed
    threshold_value REAL NOT NULL,
    fallback_used BOOLEAN NOT NULL DEFAULT FALSE,
    n_impostor_scores INTEGER,
    n_exceedances INTEGER,
    u_quantile REAL,
    u_value REAL,
    alpha REAL,
    gpd_shape REAL,
    gpd_scale REAL,
    fit_status VARCHAR(20) NOT NULL,       -- valid / warning / failed / fallback
    model_version VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexing for performance
CREATE INDEX IF NOT EXISTS idx_face_embeddings_person_id ON face_embeddings(person_id);
CREATE INDEX IF NOT EXISTS idx_recognition_events_occurred_at ON recognition_events(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_recognition_events_person_id ON recognition_events(person_id);
CREATE INDEX IF NOT EXISTS idx_recognition_events_status ON recognition_events(status);
CREATE INDEX IF NOT EXISTS idx_identity_thresholds_version ON identity_thresholds(threshold_table_version);
