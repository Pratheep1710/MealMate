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

    Numerator: rows with status == 'delivered' and `updated_at` within 10 minutes of
    `cron_fire_time`. Denominator: every row passed in (all daily_reminder rows created for that
    cron run, per MP-005 — `failed` and stuck `pending`/`sent` rows count against the numerator by
    construction, since they only enter it via the 'delivered' + in-window check above).
    """
    delivered = sum(
        1
        for n in notifications
        if n.status == "delivered" and abs(n.updated_at - cron_fire_time) <= _WINDOW
    )
    return SloResult(delivered_in_window=delivered, total=len(notifications))
