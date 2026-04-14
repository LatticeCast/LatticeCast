-- upgrade
-- 0003_add_views.sql
-- Add views JSONB column to tables for storing named view configurations

ALTER TABLE tables ADD COLUMN IF NOT EXISTS views JSONB NOT NULL DEFAULT '[]';
