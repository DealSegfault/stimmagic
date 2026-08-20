from h3_prompt_pair import (
    format_h3_prompt_pair,
    parse_h3_prompt_pair,
    select_chinese_h3_prompt,
)
import pytest


def test_h3_prompt_pair_round_trips_without_merging_languages():
    english = "integrated_multimodal_description: [Shot 1] Maya waits."
    chinese = "integrated_multimodal_description: [Shot 1] Maya保持等待。"

    encoded = format_h3_prompt_pair(english, chinese)

    assert parse_h3_prompt_pair(encoded) == {"english": english, "chinese": chinese}
    assert select_chinese_h3_prompt(encoded) == (
        chinese,
        {"english": english, "chinese": chinese},
    )


def test_non_bilingual_prompt_is_left_untouched():
    prompt = "integrated_multimodal_description: [Shot 1] A quiet room."
    assert select_chinese_h3_prompt(prompt) == (prompt, None)


@pytest.mark.asyncio
async def test_prompt_only_h3_answer_gets_a_structurally_safe_chinese_version(monkeypatch):
    import agent.v2.service as service
    import routes.prompt_enhancement as enhancement

    english = (
        "subject_definitions:\n"
        "- <Picture 1>: Maya.\n\n"
        "summary:\n"
        "A 4-second shot.\n\n"
        "retention_analysis:\n"
        "- <Picture 1>: preserve identity.\n\n"
        "detailed_description:\n"
        "<Picture 1> Maya waits.\n\n"
        "overall_soundscape:\n"
        "Quiet room.\n\n"
        "non_diegetic_music:\n"
        "N/A"
    )

    async def fake_translate(request):
        return enhancement.TranslatePromptResponse(
            translated_prompt=request.prompt.replace("Maya waits.", "Maya保持等待。")
        )

    monkeypatch.setattr(enhancement, "translate_prompt", fake_translate)
    output, metadata = await service._ensure_h3_prompt_pair(
        english,
        request_message="Donne-moi le prompt H3 en chinois",
        project_id=1,
        shot_contract={
            "expected_duration": 4,
            "reference_manifest": [{"label": "Picture 1", "media_id": 1}],
        },
    )

    pair = parse_h3_prompt_pair(output)
    assert pair == {"english": english, "chinese": english.replace("Maya waits.", "Maya保持等待。")}
    assert metadata["generation_language"] == "zh-Hans"
