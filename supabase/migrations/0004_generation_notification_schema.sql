-- MP-010: Generation and notification tables.
-- Source: version1_mealPlanner_technical.md §4. unique(user_id, week_start) on generation_jobs and
-- unique(user_id, notification_type, target_date) on notification_log are the idempotency
-- guarantees for the weekly-generation and daily-push pipelines respectively (checked before every
-- OpenAI call / every push send) — see MP-005 decision record for how notification_log feeds the SLO.

create table generation_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references user_profiles(id) on delete cascade,
  week_start date not null,
  status text not null default 'pending', -- pending | processing | done | failed
  attempts int not null default 0,
  last_error text,
  constraint generation_jobs_status_check check (
    status in ('pending', 'processing', 'done', 'failed')
  ),
  unique (user_id, week_start)
);

create table notification_log (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references user_profiles(id) on delete cascade,
  notification_type text not null,        -- week_ready | daily_reminder
  target_date date not null,              -- week_start or plan_date
  status text not null default 'pending', -- pending | sent | delivered | failed
  expo_ticket_id text,
  attempt int not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint notification_log_type_check check (
    notification_type in ('week_ready', 'daily_reminder')
  ),
  constraint notification_log_status_check check (
    status in ('pending', 'sent', 'delivered', 'failed')
  ),
  unique (user_id, notification_type, target_date)
);
