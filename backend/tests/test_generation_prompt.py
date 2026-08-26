from __future__ import annotations

import json
from dataclasses import replace

from generation_test_helpers import make_context

from app.services.generation_prompt import build_generation_prompt
from app.services.menu_validation import ValidationIssue
from app.services.slot_templates import templates_for_profile


def test_prompt_puts_static_catalogue_before_user_context() -> None:
    messages = build_generation_prompt(make_context(restrictions=["Nuts"]))

    assert [message["role"] for message in messages] == ["developer", "user"]
    static = json.loads(messages[0]["content"])
    dynamic = json.loads(messages[1]["content"])
    assert static["catalog"]
    assert "dietary_restrictions" not in static
    assert dynamic["profile"]["dietary_restrictions"] == ["Nuts"]


def test_prompt_json_is_deterministic_for_the_same_context() -> None:
    context = make_context()
    assert build_generation_prompt(context) == build_generation_prompt(context)


def test_static_prefix_does_not_change_with_user_specific_profile_values() -> None:
    context = make_context()
    other_profile = context.profile.model_copy(
        update={"dietary_restrictions": ["Nuts"], "dinner_style": "tiffin"}
    )
    other_context = replace(
        context,
        profile=other_profile,
        slot_templates=templates_for_profile(other_profile),
    )

    first = build_generation_prompt(context)
    second = build_generation_prompt(other_context)

    assert first[0] == second[0]
    assert first[1] != second[1]


def test_night_template_branches_are_explicit_and_dynamic_selection_is_authoritative() -> None:
    context = make_context(dinner_style="tiffin")
    messages = build_generation_prompt(context)
    static = json.loads(messages[0]["content"])
    dynamic = json.loads(messages[1]["content"])

    night_variants = static["slot_templates"]["night_by_dinner_style"]
    assert night_variants["rice"]["items"][0]["item_type"] == "rice"
    assert night_variants["tiffin"]["items"][0]["item_type"] == "tiffin"
    selected_night = next(
        template for template in dynamic["selected_slot_templates"] if template["slot"] == "night"
    )
    assert selected_night["items"][0]["item_type"] == "tiffin"
    assert "night_alternatives" not in static["slot_templates"]


def test_retry_feedback_is_appended_after_the_dynamic_context() -> None:
    issue = ValidationIssue("nonveg_quota", "wrong non-veg dates")
    messages = build_generation_prompt(make_context(), retry_issues=(issue,))

    assert [message["role"] for message in messages] == ["developer", "user", "user"]
    feedback = json.loads(messages[-1]["content"])
    assert feedback["retry"] is True
    assert feedback["issues"] == [{"code": "nonveg_quota", "message": "wrong non-veg dates"}]
