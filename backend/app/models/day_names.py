"""Shared day-name vocabulary for `nonveg_day_pattern`.

The column is persisted in its abbreviated form (0002_user_profile_favorites_schema.sql's own
comment: `{wed, sat}`), so both the profile model's cross-field validation and the weekly-context
computation that reads the pattern back need the same normalization — duplicating it risked exactly
the drift this module prevents (one side recognizing "wed", the other not).
"""

from __future__ import annotations

DAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

_DAY_ABBREVIATIONS = {name[:3]: name for name in DAY_NAMES}


def normalize_day_name(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in DAY_NAMES:
        return normalized
    if normalized in _DAY_ABBREVIATIONS:
        return _DAY_ABBREVIATIONS[normalized]
    raise ValueError(f"unrecognized day name: {value!r}")
