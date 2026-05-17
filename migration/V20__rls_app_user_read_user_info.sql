-- V20: Allow app_user to SELECT all rows from gdpr.user_info
-- Required for auth middleware to resolve user_name/email → user_id.
-- Without this, RLS policy user_info_self blocks the lookup (chicken-and-egg:
-- app.current_user_id isn't set yet during authentication).

CREATE POLICY user_info_app_read ON gdpr.user_info
  FOR SELECT TO app_user
  USING (true);
