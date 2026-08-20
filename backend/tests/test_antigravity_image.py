import json

import pytest
from PIL import Image

import agent.v2.tools.antigravity_image as antigravity_module
from agent.v2.service import _generation_call_key, _is_generation_tool_call
from agent.v2.tools.antigravity_image import (
    antigravity_image,
    build_antigravity_prompt,
    validate_generated_still,
)
from agent.v2.tools.run_code import run_code
from agent.v2.tools_registry import get_tool
from agent_trace_service import trace_action_for_tool


def test_validate_generated_still_requires_readable_expected_canvas(tmp_path):
    good = tmp_path / "good.png"
    Image.new("RGB", (1344, 768), "black").save(good)
    assert validate_generated_still(good, [1344, 768]) == []

    wrong_size = tmp_path / "wrong.png"
    Image.new("RGB", (1024, 576), "black").save(wrong_size)
    errors = validate_generated_still(wrong_size, [1344, 768])
    assert any("dimensions mismatch" in error for error in errors)

    unreadable = tmp_path / "broken.png"
    unreadable.write_text("not an image", encoding="utf-8")
    errors = validate_generated_still(unreadable, [1344, 768])
    assert any("not readable" in error for error in errors)


def test_build_antigravity_prompt_declares_ordered_references(tmp_path):
    prompt = build_antigravity_prompt(
        "Put the dossier on the coffee table.",
        [(161, tmp_path / "frame.png"), (49, tmp_path / "maya.png")],
        tmp_path / "plan_04_keyframe_antigravity.png",
        expected_dimensions=[1344, 768],
    )
    assert "<Picture 1> (media_id=161)" in prompt
    assert "<Picture 2> (media_id=49)" in prompt
    assert "Put the dossier on the coffee table." in prompt
    assert "exactly 1344x768 pixels" in prompt
    assert "plan_04_keyframe_antigravity.png" in prompt


def test_antigravity_image_is_registered_and_traced_as_generation():
    assert get_tool("antigravity_image") is not None
    args = json.dumps({"prompt": "edit", "reference_media_ids": [161, 49]})
    assert _is_generation_tool_call("antigravity_image", args)
    assert _generation_call_key("antigravity_image", args).startswith("antigravity_image:")

    action = trace_action_for_tool(
        "antigravity_image",
        {"prompt": "compose the opening keyframe", "reference_media_ids": [161, 49]},
    )
    assert action["kind"] == "image_generation"
    assert "Antigravity CLI" in action["label"]
    assert action["reference_media_ids"] == [161, 49]


@pytest.mark.asyncio
async def test_compose_keyframe_binds_exact_returned_media_without_calling_agy_live(monkeypatch, tmp_path):
    reference = tmp_path / "reference.png"
    Image.new("RGB", (1344, 768), "black").save(reference)

    async def fake_materialize_references(session, media_ids, workspace_dir):
        assert media_ids == [1]
        return [(1, reference)]

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            output = tmp_path / "keyframe.png"
            Image.new("RGB", (1344, 768), "white").save(output)
            return b"", b""

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess()

    async def fake_save_workspace_file(**kwargs):
        return json.dumps({"media_id": 77, "filename": "keyframe.png"})

    monkeypatch.setattr(antigravity_module, "_materialize_references", fake_materialize_references)
    monkeypatch.setattr(antigravity_module, "_agy_executable", lambda: "agy")
    monkeypatch.setattr(antigravity_module.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(antigravity_module, "save_workspace_file", fake_save_workspace_file)

    contract = {
        "workflow": "compose_opening_keyframe_then_i2v",
        "reference_manifest": [{"media_id": 1, "role": "continuity_anchor"}],
        "allowed_reference_media_ids": [1],
        "previous_last_frame_media_id": 1,
        "requires_previous_last_frame": True,
        "expected_dimensions": [1344, 768],
    }
    session_media_ids = []
    result = await antigravity_image(
        "Compose the opening keyframe.",
        reference_media_ids=[1],
        output_name="keyframe.png",
        output_role="intermediate",
        session=object(),
        workspace_dir=tmp_path,
        session_media_ids=session_media_ids,
        _shot_contract=contract,
    )

    assert "<result media_id=77" in result
    assert contract["opening_keyframe_media_id"] == 77
    assert contract["opening_keyframe_source_media_ids"] == [1]
    assert contract["opening_keyframe_backend"] == "antigravity:generate_image"
    assert session_media_ids == [77]


@pytest.mark.asyncio
async def test_compose_run_code_rejects_local_image_adapter(tmp_path):
    result = await run_code(
        "from stimma.tools.image_to_image import nano_banana_pro_edit",
        workspace_dir=tmp_path,
        session=object(),
        chat_id=1,
        _shot_contract={"workflow": "compose_opening_keyframe_then_i2v"},
    )
    assert "must use the real" in result
