-- Review fix (PR #1): MP-005's SLO measurement rule (docs/MP-005-notification-slo-decision.md)
-- defined "delivered" as `updated_at` falling within 10 minutes of the 8 PM trigger. But
-- `updated_at`'s `default now()` only fires on INSERT — Postgres never touches it on UPDATE
-- without an explicit trigger, so a later `UPDATE ... SET status = 'delivered'` would leave
-- `updated_at` at its original (on-time) INSERT value regardless of when delivery actually
-- happened, silently making late deliveries look on-time. An explicit column set atomically with
-- the status transition is the correct fix, not a generic updated_at-maintaining trigger — the SLO
-- cares specifically about the delivered transition, not "last touched".

alter table notification_log
  add column delivered_at timestamptz;
