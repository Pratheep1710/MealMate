"""Notification log table (0004_generation_notification_schema.sql). Feeds MP-005's delivery
SLO measurement — see app/services/notification_slo.py.
"""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel


class NotificationLog(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    notification_type: str
    target_date: datetime.date
    status: str
    expo_ticket_id: str | None
    attempt: int
    created_at: datetime.datetime
    updated_at: datetime.datetime
    delivered_at: datetime.datetime | None


class NotificationLogDevice(BaseModel):
    """One row per push token a notification was sent to (0020_notification_log_devices.sql) —
    the per-attempt audit trail a single notification_log row can't carry for a multi-device user.
    """

    id: uuid.UUID
    notification_log_id: uuid.UUID
    expo_push_token: str
    status: str
    expo_ticket_id: str | None
    error: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime
