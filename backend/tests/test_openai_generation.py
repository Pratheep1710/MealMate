from __future__ import annotations

from types import SimpleNamespace

import pytest
from generation_test_helpers import make_context, menu_for_context

from app.services.openai_generation import GenerationProviderError, OpenAIWeeklyMenuGenerator


class _Responses:
    def __init__(self, parsed=None, error: Exception | None = None) -> None:
        self.parsed = parsed
        self.error = error
        self.kwargs = None

    def parse(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return SimpleNamespace(output_parsed=self.parsed)


def test_adapter_uses_responses_parse_and_pydantic_schema() -> None:
    menu = menu_for_context(make_context())
    responses = _Responses(menu)
    client = SimpleNamespace(responses=responses)
    generator = OpenAIWeeklyMenuGenerator("test-key", "test-model", client=client)

    result = generator.generate([{"role": "user", "content": "context"}])

    assert result == menu
    assert responses.kwargs["model"] == "test-model"
    assert responses.kwargs["text_format"] is type(menu)
    assert responses.kwargs["store"] is False
    assert responses.kwargs["prompt_cache_key"] == "mealmate-weekly-menu-v1"


def test_adapter_wraps_sdk_failures() -> None:
    client = SimpleNamespace(responses=_Responses(error=RuntimeError("provider down")))
    generator = OpenAIWeeklyMenuGenerator("test-key", "test-model", client=client)

    with pytest.raises(GenerationProviderError, match="RuntimeError"):
        generator.generate([])


def test_adapter_rejects_missing_parsed_output() -> None:
    client = SimpleNamespace(responses=_Responses(None))
    generator = OpenAIWeeklyMenuGenerator("test-key", "test-model", client=client)

    with pytest.raises(GenerationProviderError, match="parsed weekly menu"):
        generator.generate([])
