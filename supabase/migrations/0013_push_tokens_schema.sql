-- MP-068: Expo push token registration.
-- Source: docs/MP-001 "Core" — prior-day 8 PM push notification. Tokens are keyed to user_id (not
-- device-global) per MP-068's security requirement. MP-070's send job reads across users via
-- service_role, which bypasses RLS entirely.
--
-- unique(expo_push_token), not unique(user_id, expo_push_token): a token belongs to one physical
-- device at a time. If a device is reassigned to a different account (sign-out/sign-in as someone
-- else on the same phone), registration reassigns the existing row's user_id rather than leaving a
-- stale row pointing at the previous owner.
--
-- Registration goes through register_push_token(text) below, a security-definer RPC, rather than a
-- direct RLS-scoped client insert/update (the pattern plan_items/available_ingredients use):
-- Postgres requires SELECT-policy visibility of a row before an UPDATE's WHERE clause can match it
-- (and before INSERT ... ON CONFLICT DO UPDATE can even detect the conflict) — see
-- https://www.postgresql.org/docs/current/sql-createpolicy.html's "a SELECT or ALL policy... in
-- addition to... UPDATE" note. push_tokens_select_own denies exactly the row a device handoff needs
-- to reassign (it belongs to the *other*, not-yet-current user), so a plain client-side
-- insert/update can never complete a handoff. The RPC runs as its (highly-privileged, RLS-bypassing)
-- owner and hardcodes `auth.uid()` as the row's user_id server-side, so a caller can register a
-- token only for themselves no matter what they pass in — narrower than a blanket insert/update
-- grant would be, not a workaround of RLS's intent.

create table push_tokens (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references user_profiles(id) on delete cascade,
  expo_push_token text not null unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index push_tokens_user_id_idx on push_tokens (user_id);

alter table push_tokens enable row level security;
grant select on push_tokens to authenticated;

create policy push_tokens_select_own on push_tokens
  for select to authenticated using (user_id = auth.uid());

-- No insert/update/delete policies for `authenticated`: every write goes through the RPC below.

create function register_push_token(token text)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into push_tokens (user_id, expo_push_token, updated_at)
  values (auth.uid(), token, now())
  on conflict (expo_push_token) do update
    set user_id = excluded.user_id, updated_at = now();
end;
$$;

revoke all on function register_push_token(text) from public;
grant execute on function register_push_token(text) to authenticated;
