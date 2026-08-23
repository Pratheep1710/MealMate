"""MP-005 SLO computation (app/services/notification_slo.py) — pure unit tests, no DB needed."""

from __future__ import annotations

import datetime
import uuid

from app.models import NotificationLog
from app.services.notification_slo import compute_daily_reminder_slo

_FIRE_TIME = datetime.datetime(2026, 8, 23, 20, 0, tzinfo=datetime.UTC)


def _notification(status: str, minutes_after_fire: float) -> NotificationLog:
    return NotificationLog(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        notification_type="daily_reminder",
        target_date=datetime.date(2026, 8, 23),
        status=status,
        expo_ticket_id=None,
        attempt=1,
        created_at=_FIRE_TIME,
        updated_at=_FIRE_TIME + datetime.timedelta(minutes=minutes_after_fire),
    )


def test_delivered_within_window_counts_toward_numerator():
    result = compute_daily_reminder_slo([_notification("delivered", 5)], _FIRE_TIME)
    assert result.delivered_in_window == 1
    assert result.total == 1
    assert result.ratio == 1.0
    assert result.meets_target


def test_delivered_outside_window_does_not_count():
    result = compute_daily_reminder_slo([_notification("delivered", 15)], _FIRE_TIME)
    assert result.delivered_in_window == 0
    assert result.total == 1
    assert not result.meets_target


def test_failed_and_stuck_pending_never_count_toward_numerator():
    notifications = [
        _notification("failed", 5),
        _notification("pending", 5),
        _notification("sent", 5),
    ]
    result = compute_daily_reminder_slo(notifications, _FIRE_TIME)
    assert result.delivered_in_window == 0
    assert result.total == 3


def test_ratio_across_mixed_outcomes_matches_mp005_measurement_rule():
    notifications = [_notification("delivered", 2) for _ in range(19)]
    notifications.append(_notification("failed", 2))
    result = compute_daily_reminder_slo(notifications, _FIRE_TIME)
    assert result.total == 20
    assert result.delivered_in_window == 19
    assert result.ratio == 0.95
    assert result.meets_target


def test_empty_notification_list_is_vacuously_within_target():
    result = compute_daily_reminder_slo([], _FIRE_TIME)
    assert result.total == 0
    assert result.ratio == 1.0
