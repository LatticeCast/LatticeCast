-- upgrade
-- SELECT FOR UPDATE requires UPDATE privilege, even without changing a row.
-- Only the internal cleanup role may claim queue jobs across workers.
GRANT UPDATE ON private.blob_cleanup_queue TO mgr;
