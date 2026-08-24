"""MP-005's notification delivery SLO — 95% of daily_reminder notifications delivered within 10
minutes of the 8 PM IST cron trigger (docs/MP-005-notification-slo-decision.md). This is a
query-shaped computation over notification_log, not a monitored/alerting metric in v1 (MP-005
explicitly defers that) — callers fetch rows via app.repositories.notifications and pass them in.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from app.models import NotificationLog

_WINDOW = datetime.timedelta(minutes=10)


@dataclass(frozen=True)
class SloResult:
    delivered_in_window: int
    total: int

    @property
    def ratio(self) -> float:
        return self.delivered_in_window / self.total if self.total else 1.0

    @property
    def meets_target(self) -> bool:
        return self.ratio >= 0.95


def compute_daily_reminder_slo(
    notifications: list[NotificationLog], cron_fire_time: datetime.datetime
) -> SloResult:
    """MP-005 measurement rule.

    Numerator: rows with status == 'delivered' and `delivered_at` (set atomically on the delivered
    transition — see app/repositories/notifications.py's mark_status, and migration 0008's fix for
    the `updated_at`-doesn't-update-on-UPDATE-without-a-trigger bug) falling in
    `[cron_fire_time, cron_fire_time + 10min]`. One-sided, not `abs(...)`: a delivery timestamped
    *before* the cron fire would be a clock-skew or data bug, not evidence of an on-time delivery,
    so it must not count toward the numerator. Denominator: every row passed in (all daily_reminder
    rows created for that cron run, per MP-005 — `failed` and stuck `pending`/`sent` rows count
    against the numerator by construction, since they only enter it via the checks above).
    """
    delivered = sum(
        1
        for n in notifications
        if n.status == "delivered"
        and n.delivered_at is not None
        and cron_fire_time <= n.delivered_at <= cron_fire_time + _WINDOW
    )
    return SloResult(delivered_in_window=delivered, total=len(notifications))
