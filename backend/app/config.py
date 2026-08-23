"""MP-014: typed configuration and secret loading.

Anticipates the four integration points named in the Phase 1 brief — Supabase, OpenAI, Expo,
Render — so this module doesn't need reworking when M4 (generation engine) and M6 (notifications)
start consuming it. Missing or invalid *required* config fails fast via ConfigError, listing every
problem at once (not just the first), and never includes secret values in the error message —
only field names and what's wrong with them.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from pydantic import BaseModel, Field, HttpUrl, ValidationError


class ConfigError(Exception):
    """Raised when one or more required configuration values are missing or invalid.

    The message lists every problem found across all groups, each naming the env var to set —
    never the value itself, even for fields that did resolve to something invalid.
    """


class SupabaseConfig(BaseModel):
    url: HttpUrl
    anon_key: str = Field(min_length=1)
    service_role_key: str = Field(min_length=1)


class OpenAIConfig(BaseModel):
    api_key: str = Field(min_length=1)
    model: str = Field(min_length=1)


class ExpoConfig(BaseModel):
    # Push delivery works without an access token; it's only required if Expo's "Enhanced Push
    # Notification Security" is turned on for this project — optional, not one of the fail-fast
    # required fields.
    access_token: str | None = None


class RenderConfig(BaseModel):
    # Populated automatically by Render's runtime, not user-supplied — never required locally.
    service_id: str | None = None
    git_commit: str | None = None

    @property
    def is_render(self) -> bool:
        return self.service_id is not None


class AppConfig(BaseModel):
    supabase: SupabaseConfig
    openai: OpenAIConfig
    expo: ExpoConfig
    render: RenderConfig


_SUPABASE_ENV = {
    "url": "SUPABASE_URL",
    "anon_key": "SUPABASE_ANON_KEY",
    "service_role_key": "SUPABASE_SERVICE_ROLE_KEY",
}
_OPENAI_ENV = {
    "api_key": "OPENAI_API_KEY",
    "model": "OPENAI_MODEL",
}
_EXPO_ENV = {
    "access_token": "EXPO_ACCESS_TOKEN",
}
_RENDER_ENV = {
    "service_id": "RENDER_SERVICE_ID",
    "git_commit": "RENDER_GIT_COMMIT",
}


def _validate_group[ModelT: BaseModel](
    model: type[ModelT],
    field_map: Mapping[str, str],
    source: Mapping[str, str | None],
    problems: list[str],
) -> ModelT | None:
    raw = {field: source.get(env_var) for field, env_var in field_map.items()}
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        for error in exc.errors():
            field = str(error["loc"][0])
            env_var = field_map[field]
            reason = "is missing" if error["type"] == "missing" else error["msg"]
            problems.append(f"  - {env_var} {reason}")
        return None


def load_config(env: Mapping[str, str] | None = None) -> AppConfig:
    """Load and validate configuration from environment variables.

    Raises ConfigError with one line per problem field (env var name + reason, never the value)
    if any required field across any group is missing or fails validation. Optional groups
    (Expo, Render) never raise — their fields default to None when absent.
    """
    source = env if env is not None else os.environ

    problems: list[str] = []
    supabase = _validate_group(SupabaseConfig, _SUPABASE_ENV, source, problems)
    openai = _validate_group(OpenAIConfig, _OPENAI_ENV, source, problems)
    expo = _validate_group(ExpoConfig, _EXPO_ENV, source, problems)
    render = _validate_group(RenderConfig, _RENDER_ENV, source, problems)

    if problems:
        raise ConfigError(
            "Configuration is invalid — fix the following environment variables:\n"
            + "\n".join(problems)
        )

    assert supabase is not None
    assert openai is not None
    assert expo is not None
    assert render is not None
    return AppConfig(supabase=supabase, openai=openai, expo=expo, render=render)
