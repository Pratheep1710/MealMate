-- MP-070 review fix (PR #10): 'processing' status for notification_log, mirroring
-- generation_jobs' pending -> processing claim (0004/0010). Without an intermediate state, two
-- overlapping runs (a scheduled run and a manual workflow_dispatch, or two retried Actions jobs)
-- could both upsert the same 'pending' row, both see it as sendable, and both call Expo's push
-- API before either marks the row 'sent' — the unique(user_id, notification_type, target_date)
-- constraint prevents a duplicate *row*, not a duplicate *push*. See
-- app/repositories/notifications.py's try_claim for the atomic pending/failed -> processing
-- transition this status now supports.

alter table notification_log drop constraint notification_log_status_check;

alter table notification_log add constraint notification_log_status_check check (
  status in ('pending', 'processing', 'sent', 'delivered', 'failed')
);
