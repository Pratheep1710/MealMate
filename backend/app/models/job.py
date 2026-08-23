"""Generation job table (0004_generation_notification_schema.sql)."""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel


class GenerationJob(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    week_start: datetime.date
    status: str
    attempts: int
    last_error: str | None
