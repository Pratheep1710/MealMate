# MP-005 — Notification Delivery SLO: Decision Record

**Decision: 95% of notifications delivered within 10 minutes of the 8 PM IST cron trigger.**

## Rationale
- Adopts, as the real target, the placeholder already reasoned about in technical spec §8 ("something
  like 95% delivered within 10 minutes of the 8 PM trigger — labeled here as a guess, not a
  benchmark"). No new number invented; this decision formally promotes it from guess to target.
- The notification *is* the product's core value-delivery path (technical spec §7 decision log) and
  fails silently by design if missed — a defined, even if rough, target is better than none, and can
  be recalibrated once real delivery data exists (technical spec §8 explicitly anticipates this).

## Measurement rule
- **Numerator:** rows in `notification_log` where `notification_type = 'daily_reminder'` and
  `status = 'delivered'`, with `delivered_at` within 10 minutes of that day's 8 PM IST cron fire
  time.
- **Denominator:** all `daily_reminder` rows created for that day's cron run (i.e., all users
  eligible for a reminder that evening), regardless of eventual status.
- **Window:** rolling 7-day measurement, recomputed daily, once real usage exists — not enforced
  per-night in v1 (no dashboard/alerting per technical spec §7's deferred item).
- `status = 'failed'` and stuck `'pending'`/`'sent'` rows beyond the reconciliation job's ~30-minute
  window both count against the numerator (i.e., are treated as not-delivered-in-window).

## What this means for downstream tasks
- `notification_log` (MP-010) needed one addition: a `delivered_at` column (migration `0008`,
  PR #1 review). The original plan to reuse `updated_at` as the delivered timestamp was wrong —
  Postgres's `default now()` only fires on INSERT, so `updated_at` never actually reflects when a
  row transitioned to `delivered` without an explicit trigger, which would have silently let late
  deliveries measure as on-time. The reconciliation job (technical spec §2.2) must set
  `delivered_at = now()` atomically with the `status = 'delivered'` write, not rely on any default.
- No automated alerting on this SLO in v1 (technical spec §7/§8 already defer that) — it's a query
  against `notification_log`, not a monitored/paged metric yet.

## Revisit trigger
Real delivery data from production use — recalibrate the 95%/10-minute numbers once actual variance
in Expo/APNs/FCM delivery times is observed, per technical spec §8's own framing of this as a
starting point, not a benchmark.
