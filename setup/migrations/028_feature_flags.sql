-- Migration: Create feature_flags table supporting multi-stage lifecycle
-- 028_feature_flags.sql


CREATE TABLE IF NOT EXISTS feature_flags (
    flag_key TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('off', 'dev_only', 'testing', 'prod_test', 'on')),
    allowed_users TEXT[] NOT NULL DEFAULT '{}',
    description TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed initial row for auth wrapper gating in dev
INSERT INTO feature_flags (flag_key, status, allowed_users, description)
VALUES (
    'auth_wrapper_enabled', 
    'dev_only', 
    '{}', 
    'Gate-flag for Supabase Auth wrapper rollout on internal apps (TinySteps / Growth Spurt)'
)
ON CONFLICT (flag_key) DO NOTHING;
