"""MP-040 OpenAI Responses API adapter for structured weekly menus."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, cast

from openai import OpenAI

from app.schemas.weekly_menu import WeeklyMenu
from app.services.generation_prompt import PromptMessage


class GenerationProviderError(Exception):
    """A provider/refusal/parse failure that may consume the one retry budget."""


class WeeklyMenuGenerator(Protocol):
    def generate(self, messages: Sequence[PromptMessage]) -> WeeklyMenu: ...


class OpenAIWeeklyMenuGenerator:
    def __init__(self, api_key: str, model: str, *, client: Any | None = None) -> None:
        self._model = model
        self._client = client if client is not None else OpenAI(api_key=api_key)

    def generate(self, messages: Sequence[PromptMessage]) -> WeeklyMenu:
        try:
            response = self._client.responses.parse(
                model=self._model,
                input=cast(Any, list(messages)),
                text_format=WeeklyMenu,
                store=False,
                prompt_cache_key="mealmate-weekly-menu-v1",
            )
        except Exception as exc:
            # Keep SDK/provider details behind this boundary. The caller logs only the exception
            # type, never an SDK message that could echo request or response content.
            raise GenerationProviderError(type(exc).__name__) from exc
        parsed = response.output_parsed
        if not isinstance(parsed, WeeklyMenu):
            raise GenerationProviderError("OpenAI response did not contain a parsed weekly menu")
        return parsed
