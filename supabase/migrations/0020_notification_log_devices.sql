-- PR review fix (Phase 7): MP-071's "auditable status" requirement is per notification, not per
-- device. A user with more than one registered push token previously had only their *last*
-- send's ticket id remembered on the single notification_log row — with two successful sends only
-- the last one's receipt ever got reconciled, and with one success + one failure the failed
-- device's attempt vanished entirely while the row read 'sent'. This table gives every token its
-- own send/delivery record, so every attempt is auditable and every ticket gets reconciled.
--
-- notification_log itself keeps its existing meaning unchanged: the per (user, type, date)
-- idempotency/claim row the send pipeline's try_claim guards (0015). Its aggregate status is now
-- synced from these device rows (see app/repositories/notifications.py's
-- sync_notification_status_from_devices) rather than written directly from a single ticket.

create table notification_log_devices (
  id uuid primary key default gen_random_uuid(),
  notification_log_id uuid not null references notification_log(id) on delete cascade,
  expo_push_token text not null,
  status text not null default 'sent', -- sent | delivered | failed
  expo_ticket_id text,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint notification_log_devices_status_check check (
    status in ('sent', 'delivered', 'failed')
  )
);

create index notification_log_devices_log_id_idx on notification_log_devices (notification_log_id);
create index notification_log_devices_reconcile_idx
  on notification_log_devices (status, updated_at)
  where status = 'sent';

alter table notification_log_devices enable row level security;
grant select on notification_log_devices to authenticated;

create policy notification_log_devices_select_own on notification_log_devices
  for select to authenticated using (
    exists (
      select 1 from notification_log nl
      where nl.id = notification_log_devices.notification_log_id
        and nl.user_id = auth.uid()
    )
  );
