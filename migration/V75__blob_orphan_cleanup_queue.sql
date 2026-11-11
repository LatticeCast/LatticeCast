-- upgrade
-- A blob may reach storage before its row transaction starts. If that row is
-- deleted during upload, the manager cleanup worker must be able to queue
-- the now-orphaned key without relying on the vanished row or app RLS.
GRANT INSERT ON private.blob_cleanup_queue TO mgr;
