"""Push token table (0013_push_tokens_schema.sql). Registered client-side (direct RLS-scoped
write, mobile/src/lib/pushRegistration.ts) — MP-070's send job reads across users here via the
service_role connection, which bypasses RLS.
"""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel


class PushToken(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    expo_push_token: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
