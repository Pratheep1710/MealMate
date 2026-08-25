-- MP-068 review fix (PR #10): unregister a device's push token on sign-out.
--
-- register_push_token (0013) reassigns a token to whoever signs in next on the same device, but
-- nothing previously removed the row when a user signed *out* — so a device sitting at the
-- sign-in screen (no one signed in yet) kept receiving the previous user's meal reminders, which
-- MP-068's "tokens are keyed to user_id" security requirement doesn't allow.
--
-- Mirrors register_push_token's security-definer pattern for the same reason: push_tokens_select_own
-- denies a row belonging to another user, but here the caller *is* the row's owner and is about to
-- sign out — a security-definer function sidesteps the ordering issue (delete must happen while
-- still authenticated) rather than any RLS gap. Scoped to the caller's own auth.uid() and a
-- specific token value (not "delete everything for this user") so signing out on one device never
-- silently unregisters a different device the same account is still signed into elsewhere.

create function unregister_push_token(token text)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  delete from push_tokens where expo_push_token = token and user_id = auth.uid();
end;
$$;

revoke all on function unregister_push_token(text) from public;
grant execute on function unregister_push_token(text) to authenticated;
