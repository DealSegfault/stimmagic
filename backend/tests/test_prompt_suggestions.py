from routes.prompt_enhancement import CategoryItem, _stabilize_suggestion_categories


def test_central_human_prompt_gets_stable_core_categories():
    categories = [
        CategoryItem(label="Lighting", category="lighting"),
        CategoryItem(label="Setting", category="setting"),
    ]

    result = _stabilize_suggestion_categories(
        "A portrait of a woman in a rain-soaked alley", categories
    )

    keys = [item.category for item in result]
    assert keys[:6] == [
        "expression",
        "pose",
        "outfit",
        "hair_style",
        "hair_color",
        "age",
    ]
    assert "lighting" in keys
    assert "setting" in keys


def test_identity_categories_pass_through_unchanged():
    """We no longer drop or relabel ethnicity/heritage based on the prompt — the
    model's choice is trusted as-is (only 'race' is banned)."""
    categories = [
        CategoryItem(label="Ethnicity", category="ethnicity", allow_wildcard=True),
        CategoryItem(label="Lighting", category="lighting"),
    ]
    # Prompt does NOT mention identity, yet ethnicity survives and keeps its label.
    result = _stabilize_suggestion_categories(
        "A portrait of a woman in a rain-soaked alley", categories
    )
    by_key = {c.category: c for c in result}
    assert "ethnicity" in by_key
    assert by_key["ethnicity"].label == "Ethnicity"  # not collapsed to "Heritage"
    assert "lighting" in by_key


def test_categories_capped_at_20():
    cats = [CategoryItem(label=f"C{i}", category=f"c{i}") for i in range(40)]
    # Non-human prompt → straight pass-through, capped.
    assert len(_stabilize_suggestion_categories("a vast landscape", cats)) == 20


def test_suggest_request_models_accept_instructions_and_thinking():
    """Suggestions carry the tool's standing Instructions + the thinking flag
    (TOOLVIEW_INTELLIGENCE #1 follow-on). Older callers omit them → defaults."""
    from routes.prompt_enhancement import (
        SuggestCategoriesRequest,
        SuggestOptionsRequest,
        SuggestOptionsBatchRequest,
    )

    cat = SuggestCategoriesRequest(prompt="a dog", instructions="prefer mountain breeds", thinking=True)
    assert cat.instructions == "prefer mountain breeds" and cat.thinking is True

    opt = SuggestOptionsRequest(prompt="a dog", category=CategoryItem(label="Breed", category="breed"))
    assert opt.instructions is None and opt.thinking is False  # defaults

    batch = SuggestOptionsBatchRequest(prompt="a dog", categories=[], instructions="x", thinking=True)
    assert batch.instructions == "x" and batch.thinking is True


def test_llm_complete_text_supports_enable_thinking():
    import inspect
    from llm import llm_complete_text
    params = inspect.signature(llm_complete_text).parameters
    assert "enable_thinking" in params
    assert params["enable_thinking"].default is False  # off unless asked


def test_parse_options_merges_multiple_arrays():
    """Small models sometimes emit several arrays instead of one; the parser must
    merge + dedupe rather than choke with a JSON 'Extra data' error (returning 0)."""
    from routes.prompt_enhancement import _parse_options_response
    multi = '["Midnight blue", "Raven"]\n["Jet black", "Raven"]\n["Black", "Auburn"]'
    options, refusal = _parse_options_response(multi)
    assert refusal is None
    assert options == ["Midnight blue", "Raven", "Jet black", "Black", "Auburn"]


def test_parse_options_handles_prose_wrapped_array():
    from routes.prompt_enhancement import _parse_options_response
    options, _ = _parse_options_response('Sure! ["x", "y", "x"] done')
    assert options == ["x", "y"]


def test_instructions_bypass_central_human_core_forcing():
    """With standing Instructions, the model's instruction-driven categories win —
    we don't force the central-human core set (Expression/Pose/Outfit/...)."""
    from routes.prompt_enhancement import _stabilize_suggestion_categories
    model_cats = [
        CategoryItem(label="Mood", category="mood"),
        CategoryItem(label="Lighting", category="lighting"),
        CategoryItem(label="Camera Lens", category="camera_lens"),
    ]
    # Default (no instructions): a human prompt forces the core dimensions.
    forced = _stabilize_suggestion_categories("a portrait of a woman", list(model_cats))
    assert "expression" in [c.category for c in forced]
    # With instructions: pass the model's categories through unchanged.
    kept = _stabilize_suggestion_categories(
        "a portrait of a woman", list(model_cats), has_instructions=True
    )
    assert [c.category for c in kept] == ["mood", "lighting", "camera_lens"]


import pytest
from fastapi import HTTPException
from unittest.mock import patch


@pytest.mark.asyncio
async def test_suggest_categories_maps_llm_unavailable_to_coded_http_error():
    """No-LLM must surface as a coded 400 (with a CTA on the client), never a
    bare 500 from the global handler."""
    from llm_resolver import LLMNotConfiguredError
    from routes.prompt_enhancement import SuggestCategoriesRequest, suggest_categories

    async def unavailable(role, project_id=None):
        raise LLMNotConfiguredError("No chat model is configured.")

    with patch("llm_resolver.get_effective_llm_config", side_effect=unavailable):
        with pytest.raises(HTTPException) as exc:
            await suggest_categories(SuggestCategoriesRequest(prompt="a red fox"))

    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "llm_not_configured"


@pytest.mark.asyncio
async def test_suggest_options_maps_llm_unavailable_to_coded_http_error():
    from llm_resolver import LLMInsufficientBalanceError
    from routes.prompt_enhancement import (
        CategoryItem as SuggestCategoryInput,
        SuggestOptionsRequest,
        _suggest_options_impl,
    )

    async def unavailable(role, project_id=None):
        raise LLMInsufficientBalanceError("Your Stimma account has no credits.")

    request = SuggestOptionsRequest(
        prompt="a red fox",
        category=SuggestCategoryInput(label="Lighting", category="lighting", allow_wildcard=True),
    )
    with patch("llm_resolver.get_effective_llm_config", side_effect=unavailable):
        with pytest.raises(HTTPException) as exc:
            await _suggest_options_impl(request)

    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "llm_insufficient_balance"


@pytest.mark.asyncio
async def test_suggest_options_batch_propagates_uniform_llm_error():
    """All categories failing on LLM availability collapses to one coded error."""
    from llm_resolver import LLMNotConfiguredError
    from routes.prompt_enhancement import (
        CategoryItem as SuggestCategoryInput,
        SuggestOptionsBatchRequest,
        suggest_options_batch,
    )

    async def unavailable(role, project_id=None):
        raise LLMNotConfiguredError("No chat model is configured.")

    request = SuggestOptionsBatchRequest(
        prompt="a red fox",
        categories=[
            SuggestCategoryInput(label="Lighting", category="lighting", allow_wildcard=True),
            SuggestCategoryInput(label="Mood", category="mood", allow_wildcard=False),
        ],
    )
    with patch("llm_resolver.get_effective_llm_config", side_effect=unavailable):
        with pytest.raises(HTTPException) as exc:
            await suggest_options_batch(request)

    assert exc.value.detail["code"] == "llm_not_configured"
