-- upgrade
-- V36: Per-user mutable settings on public.user_info.
--
-- A new `config` JSONB column holds anything we want to persist per user
-- across browsers and devices: dark-mode preference, last-viewed view per
-- (workspace, table), etc.
--
-- The column is non-PII (UI preferences only) so it lives in
-- public.user_info, not auth.gdpr.

ALTER TABLE public.user_info
ADD COLUMN IF NOT EXISTS config JSONB NOT NULL DEFAULT '{}'::JSONB;
