"""Video review gates, exact versions, settings sync and sequential execution."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.v2.code_runtime import StimmaSDK, ToolResult
from agent.v2.tools.run_code import run_code
from agent.v2.service import _pause_for_ask_user, interrupt_execution
from agent.v2.video_plan import (
    normalize_plan, plan_key, preparation_errors, prepare_review,
    read_settings, record_review, validate_dispatch, preserve_video_plan,
    asset_preparation_needs_continuation,
)
from agent.v2.video_settings import h3_timing
from shot_continuity_service import validate_shot_output
from tests.helpers.media import create_media_item


@pytest.mark.asyncio
@pytest.mark.parametrize("backend,case", [
    ("bash", "next_asset"),
    ("antigravity_image", "next_asset"),
    ("run_code", "next_asset"),
    ("bash", "duplicate"),
    ("bash", "no_plan"),
    ("bash", "complete_plan"),
])
async def test_agent_loop_continues_planned_assets_after_show_until_collective_review(
    session, test_chat, tmp_path, monkeypatch, backend, case,
):
    from agent.v2 import service
    from database import ChatItem
    from llm import LLMResponse, ToolCall
    from tests.helpers.media import generate_test_image

    ws = SimpleNamespace(broadcast=AsyncMock())
    monkeypatch.setattr(service, "_interrupt_flags", {})
    monkeypatch.setattr(service, "get_workspace_dir", lambda *args: tmp_path)
    monkeypatch.setattr(service, "get_project_workspace", lambda *args: None)
    monkeypatch.setattr(service, "resolve_agent_config", AsyncMock(return_value=SimpleNamespace(
        additional_instructions="", global_memory="", project_memory="",
    )))
    monkeypatch.setattr(service, "get_system_prompt", lambda **kwargs: "Prepare the requested assets.")
    monkeypatch.setattr(service, "get_chat_llm_config", AsyncMock(return_value=SimpleNamespace(
        model="test", max_context_tokens=128_000,
    )))
    monkeypatch.setattr(service, "_needs_permission", AsyncMock(return_value=False))
    monkeypatch.setattr("utils.websocket.ws_manager", ws)
    monkeypatch.setattr("agent.v2.stimpacks.list_skills", lambda: [])
    monkeypatch.setattr("agent.v2.tool_fs.ensure_task_tools", AsyncMock())
    monkeypatch.setattr("agent.v2.tool_fs.materialize_tool_fs", lambda *args: None)
    monkeypatch.setattr("providers.registry.ProviderRegistry.get_instance", lambda: SimpleNamespace(list_all_tools=lambda: []))

    media = []
    for name in ("K2", "K3A"):
        path = tmp_path / f"{name}.png"
        generate_test_image(path)
        media.append(await create_media_item(session, file_path=path))
    if case != "no_plan":
        assets = [{"name": "K2", "media_id": None}]
        if case != "complete_plan":
            assets.append({"name": "K3A", "media_id": None})
        test_chat.generation_settings = json.dumps({"_video_plan": normalize_plan({
            "target_duration": 30, "assets": assets, "clips": [],
        })})
    session.add(ChatItem(chat_id=test_chat.id, item_type="user_message", message_text=
        "Continue all remaining assets to the collective review. No video before my agreement."))
    await session.commit()

    generated = []
    real_get_tool = service.get_tool

    async def fake_generate(**kwargs):
        generated.append(kwargs)
        return "Generated the requested still image."

    def get_tool(name, **kwargs):
        # Only the paid generation is simulated; show, SDK registration,
        # conversation rebuilding and the review pause use the real runtime.
        descriptor = real_get_tool(name, **kwargs)
        if name == backend:
            async def handler(**args):
                if service._is_generation_tool_call(name, json.dumps(args, default=str)):
                    return await fake_generate(**args)
                return await descriptor.handler(**args)
            return SimpleNamespace(handler=handler)
        return descriptor

    monkeypatch.setattr(service, "get_tool", get_tool)
    responses = []

    def call(name, arguments, content=""):
        responses.append(LLMResponse(content=content, model="test", tool_calls=[ToolCall(
            id=f"call_{len(responses)}", name=name, arguments=json.dumps(arguments),
        )]))

    def generation(name):
        if backend == "bash":
            return {"command": f"codex exec 'Generate {name}, save as {name}.png'"}
        if backend == "antigravity_image":
            return {"prompt": f"Generate {name}"}
        return {"code": f"from stimma.tools.text_to_image import generate\nr = await generate(prompt='{name}')"}

    def register(index):
        if case == "no_plan":
            code = "print('Image displayed')"
        else:
            code = f"""
plan = await stimma.video_plan()
plan['assets'][{index}]['media_id'] = {media[index].id}
await stimma.video_plan({{key: plan[key] for key in ('target_duration', 'assets', 'clips')}})
"""
        call("run_code", {"code": code})

    call(backend, generation("K2"))
    call("show", {"media_id": media[0].id, "role": "final"})
    register(0)
    call(backend, generation("K2" if case == "duplicate" else "K3A"), "Je génère K3A.")
    if case == "next_asset":
        call("show", {"media_id": media[1].id, "role": "final"})
        register(1)
        call("ask_user", {"question": "Review all assets?", "video_review": {"media_ids": [item.id for item in media]}})
    completion = AsyncMock(side_effect=responses)
    monkeypatch.setattr(service, "llm_completion", completion)

    await service._run_agentic_loop_inner(test_chat, session, ws, max_turns=10)
    if case == "next_asset":
        assert len(generated) == 2
        settings = read_settings(test_chat)
        assert settings["_v2_ask_pending"]["video_review"]["media_ids"] == [item.id for item in media]
        assert settings["_video_plan"]["authorized_key"] is None
    else:
        assert len(generated) == 1
        assert completion.await_count == 4


@pytest.mark.asyncio
async def test_video_help_is_accessible_in_the_real_sandbox_and_documents_preparation(session, test_chat, tmp_path, monkeypatch):
    monkeypatch.setattr("utils.websocket.ws_manager", SimpleNamespace(broadcast=AsyncMock()))
    # Preparation must work even when the remote H3 provider is offline.
    monkeypatch.setattr("providers.registry.ProviderRegistry.get_instance", lambda: SimpleNamespace(list_all_tools=lambda: []))
    output = await run_code(
        code="""
print(sdk_help())
print(sdk_help('video'))
print(sdk_help('video_plan'))
timing = await stimma.video_settings(duration=4)
assert timing['effective_duration'] == 107 / 24
plan = await stimma.video_plan({'target_duration': 30, 'assets': [{'name': 'Opening keyframe', 'media_id': None}], 'clips': []})
assert plan['target_duration'] == 30
assert plan['authorized_key'] is None
plan = await stimma.video_plan({'target_duration': 30, 'assets': plan['assets'], 'clips': [{'id': 'Opening shot', 'tool_id': 'comfyui:minimax_h3_t2v', 'duration': 4, 'edit_duration': 4, 'parameters': {}}]})
assert plan['clips'][0]['id'] == 'Opening shot'
print(plan['pending'])
""",
        session=session, chat_id=test_chat.id, workspace_dir=tmp_path,
        project_workspace_dir=None, interrupt_checker=None,
    )
    assert not output.startswith("Error"), output
    assert "Video preparation" in output
    assert "edit_duration" in output and "tool_id" in output
    assert "Opening keyframe" in output and "assets" in output


def test_video_plan_invalid_shapes_point_to_the_accessible_schema():
    with pytest.raises(ValueError, match="print\\(sdk_help\\('video_plan'\\)\\)") as error:
        normalize_plan({"title": "Film", "total_duration": 30, "resolution": "720", "steps": 8, "assets": [], "clips": []})
    assert "unsupported fields" in str(error.value)
    assert "stimma.video_settings" in str(error.value)
    with pytest.raises(ValueError, match="edit_duration") as error:
        normalize_plan({"target_duration": 30, "assets": [], "clips": [{"id": "clip_1", "title": "The threshold", "duration": 4}]})
    assert "print(sdk_help('video_plan'))" in str(error.value)


def test_preparing_an_asset_continues_to_collective_review_but_reading_a_plan_does_not():
    before = normalize_plan(draft())
    before["assets"].append({"name": "K2", "media_id": None})
    before["assets"].append({"name": "K3", "media_id": None})
    assert not asset_preparation_needs_continuation(None, before)
    assert not asset_preparation_needs_continuation(before, before)
    after = json.loads(json.dumps(before))
    after["assets"][1]["media_id"] = 2
    assert asset_preparation_needs_continuation(before, after)
    assert asset_preparation_needs_continuation(after, after, continuing=True)
    after["assets"][2]["media_id"] = 3
    assert asset_preparation_needs_continuation(before, after)  # Ready images still need their collective review.
    after["approved_media_ids"] = [1, 2, 3]
    assert not asset_preparation_needs_continuation(before, after, continuing=True)
    assert not asset_preparation_needs_continuation(before, None, continuing=True)


def draft(media_id=1):
    return {
        "target_duration": 30,
        "assets": [{"name": "Reference", "media_id": media_id}],
        "clips": [
            {"id": f"Shot {index}", "tool_id": "comfyui:minimax_h3_i2v", "duration": duration,
             "edit_duration": edit, "parameters": {"prompt": f"Action {index}", "input_images": [media_id]}}
            for index, duration, edit in [(1, 6, 6), (2, 12, 12), (3, 12, 12)]
        ],
    }


def approve(settings, review):
    pending, _ = prepare_review(settings, review)
    record_review(settings, {"video_review": pending}, pending["label"])


def dispatch(settings, index=0, **overrides):
    plan = settings["_video_plan"]
    clip = plan["clips"][index]
    validate_dispatch(settings, **{
        "clip_id": clip["id"], "key": plan_key(plan), "tool_id": clip["tool_id"],
        "parameters": clip["parameters"], "effective_duration": clip["duration"], **overrides,
    })


def test_collective_asset_review_and_start_are_distinct_and_ordered():
    value = draft()
    value["assets"].append({"name": "Ending keyframe", "media_id": 2})
    settings = {"_video_plan": normalize_plan(value)}
    with pytest.raises(ValueError, match="Review"):
        dispatch(settings)
    pending, _ = prepare_review(settings, {"media_ids": [1, 2]})
    record_review(settings, {"video_review": pending}, "Modifier")
    assert settings["_video_plan"]["approved_media_ids"] == []
    approve(settings, {"media_ids": [1]})
    with pytest.raises(ValueError, match="Review"):
        dispatch(settings)
    approve(settings, {"media_ids": [1, 2]})
    assert settings["_video_plan"]["approved_media_ids"] == [1, 2]
    assert settings["_video_plan"]["authorized_key"] is None
    with pytest.raises(ValueError, match="explicitly start"):
        dispatch(settings)
    approve(settings, {"start": True})
    dispatch(settings)
    with pytest.raises(ValueError, match="sequentially"):
        dispatch(settings, index=1)
    with pytest.raises(ValueError, match="differs"):
        dispatch(settings, effective_duration=5)
    settings["_video_plan"]["outputs"]["Shot 1"] = 99
    dispatch(settings, index=1)


def test_asset_versions_and_plan_changes_invalidate_approvals():
    settings = {"_video_plan": normalize_plan(draft())}
    approve(settings, {"media_ids": [1]})
    pending, _ = prepare_review(settings, {"start": True})
    changed = draft()
    changed["clips"][0]["parameters"]["prompt"] = "A changed action"
    settings["_video_plan"] = normalize_plan(changed, settings["_video_plan"])
    record_review(settings, {"video_review": pending}, pending["label"])
    assert settings["_video_plan"]["authorized_key"] is None
    assert settings["_video_plan"]["approved_media_ids"] == [1]
    replaced = normalize_plan(draft(2), settings["_video_plan"])
    assert replaced["approved_media_ids"] == []
    with pytest.raises(ValueError, match="approvals belong"):
        normalize_plan({**draft(), "approved_media_ids": [1]})
    assert preserve_video_plan(settings, {"video_duration": 8})["_video_plan"] == settings["_video_plan"]
    assert "_video_plan" not in preserve_video_plan({}, settings)


def test_missing_assets_prompts_duration_and_wrong_mode_block_preparation():
    value = draft()
    value["assets"].append({"name": "Ending keyframe", "media_id": None})
    value["clips"][0]["parameters"]["prompt"] = ""
    value["clips"][0]["edit_duration"] = 5
    issues = preparation_errors(normalize_plan(value))
    assert any("Ending keyframe" in issue for issue in issues)
    assert any("prompt" in issue for issue in issues)
    assert any("sum" in issue for issue in issues)
    value = draft()
    value["clips"][0]["parameters"]["input_images"] = [1, 2]
    with pytest.raises(ValueError, match="I2V requires exactly one"):
        normalize_plan(value)
    assert h3_timing(6) == {"fps": 24, "frame_count": 158, "effective_duration": 158 / 24}


@pytest.mark.asyncio
async def test_sdk_settings_and_hitl_persist_exact_reviews(session, test_chat, tmp_path, monkeypatch):
    monkeypatch.setattr("agent.v2.service._interrupt_flags", {})
    ws = SimpleNamespace(broadcast=AsyncMock())
    monkeypatch.setattr("utils.websocket.ws_manager", ws)
    path = tmp_path / "asset.png"
    path.write_bytes(b"reference")
    media = await create_media_item(session, file_path=path)
    test_chat.generation_settings = json.dumps({"image_backend": "antigravity", "_v2_ask_pending": {"keep": True}})
    await session.commit()
    sdk = StimmaSDK(session=session, chat_id=test_chat.id, workspace_dir=tmp_path, project_workspace_dir=None, interrupt_checker=lambda: False)
    current = await sdk.video_settings(duration=6)
    assert current["frame_count"] == 158
    await sdk.video_plan(draft(media.id))
    await session.refresh(test_chat)
    assert read_settings(test_chat)["image_backend"] == "antigravity"
    assert read_settings(test_chat)["_v2_ask_pending"] == {"keep": True}
    await _pause_for_ask_user(test_chat, session, ws, "review1", 0, {"question": "Review reference", "video_review": {"media_ids": [media.id]}})
    settings = read_settings(test_chat)
    pending = settings["_v2_ask_pending"]
    record_review(settings, pending, pending["video_review"]["label"])
    approve(settings, {"start": True})
    test_chat.generation_settings = json.dumps(settings)
    await session.commit()
    assert (await sdk.video_plan())["approved_media_ids"] == [media.id]
    await sdk.video_settings(duration=12)
    assert (await sdk.video_plan())["authorized_key"]
    await sdk.video_settings(resolution="480")
    assert (await sdk.video_plan())["authorized_key"] is None
    assert ws.broadcast.await_args[0][0] == "chat_updated"


@pytest.mark.asyncio
async def test_series_runs_sequentially_shows_each_clip_and_resumes(session, test_chat, tmp_path, monkeypatch):
    monkeypatch.setattr("agent.v2.service._interrupt_flags", {})
    from contextlib import asynccontextmanager
    holds = []

    @asynccontextmanager
    async def video_sequence():
        holds.append("begin")
        try:
            yield "f" * 32
        finally:
            holds.append("end")

    monkeypatch.setattr("utils.websocket.ws_manager", SimpleNamespace(broadcast=AsyncMock()))
    monkeypatch.setattr("agent.v2.tool_permission_gate.ensure_tool_permission", AsyncMock())
    descriptor = SimpleNamespace(parameter_schema={"properties": {"prompt": {}, "input_images": {}, "duration": {}, "steps": {}}})
    provider = SimpleNamespace(provider_id="comfyui-modal-h3", video_sequence=video_sequence)
    monkeypatch.setattr("providers.registry.ProviderRegistry.get_instance", lambda: SimpleNamespace(get_tool=lambda _: (provider, descriptor)))
    path = tmp_path / "asset.png"
    path.write_bytes(b"reference")
    media = await create_media_item(session, file_path=path)
    sdk = StimmaSDK(session=session, chat_id=test_chat.id, workspace_dir=tmp_path, project_workspace_dir=None, interrupt_checker=lambda: False)
    await sdk.video_plan(draft(media.id))
    await session.refresh(test_chat)
    settings = read_settings(test_chat)
    approve(settings, {"media_ids": [media.id]})
    approve(settings, {"start": True})
    test_chat.generation_settings = json.dumps(settings)
    await session.commit()
    events = []
    active = 0
    fail_once = True

    async def fake_dispatch(tool_id, **params):
        nonlocal active, fail_once
        assert params["_video_sequence_id"] == "f" * 32
        assert holds[-1] == "begin"
        active += 1
        assert active == 1
        if params["_video_plan_clip"] == "Shot 2" and fail_once:
            fail_once = False
            active -= 1
            raise RuntimeError("provider failed")
        await asyncio.sleep(0)
        async with session.bind.connect() as connection:
            # The next generation sees the same duration as the bottom control.
            raw = await connection.exec_driver_sql("SELECT generation_settings FROM chats WHERE id = ?", (test_chat.id,))
            assert json.loads(raw.scalar())["video_duration"] == params["duration"]
        events.append(("generate", params["_video_plan_clip"], params["duration"]))
        active -= 1
        output = await create_media_item(session, file_format="mp4", tool_id=tool_id, duration=h3_timing(params["duration"])["effective_duration"])
        return ToolResult(path=Path("/fake.mp4"), media_id=output.id)

    sdk._dispatch_tool = fake_dispatch
    sdk.show = lambda result, **kwargs: events.append(("show", kwargs["title"]))
    sdk.flush = AsyncMock(side_effect=lambda: events.append(("flush",)))
    wrong = draft(media.id)
    wrong["clips"][1]["parameters"]["steps"] = 8
    await sdk.video_plan(wrong)
    await session.refresh(test_chat)
    settings = read_settings(test_chat)
    approve(settings, {"start": True})
    test_chat.generation_settings = json.dumps(settings)
    await session.commit()
    with pytest.raises(ValueError, match="Prepared steps differs"):
        await sdk.generate_video_plan()
    assert events == []
    assert holds == []  # Bad preparation cannot warm a GPU.
    await sdk.video_plan(draft(media.id))
    await session.refresh(test_chat)
    settings = read_settings(test_chat)
    approve(settings, {"start": True})
    test_chat.generation_settings = json.dumps(settings)
    await session.commit()
    with pytest.raises(RuntimeError, match="provider failed"):
        await sdk.generate_video_plan()
    assert holds == ["begin", "end"]
    assert list((await sdk.video_plan())["outputs"]) == ["Shot 1"]
    results = await sdk.generate_video_plan()
    assert holds == ["begin", "end", "begin", "end"]
    assert len(results) == 2
    assert [event[0] for event in events] == ["generate", "show", "flush"] * 3
    assert [event[2] for event in events if event[0] == "generate"] == [6, 12, 12]
    assert len((await sdk.video_plan())["outputs"]) == 3
    assert await sdk.generate_video_plan() == []
    await session.refresh(test_chat)
    await interrupt_execution(test_chat, session, SimpleNamespace(broadcast=AsyncMock()))
    assert (await sdk.video_plan())["authorized_key"] is None
    sdk.project_id = 1
    with pytest.raises(ValueError, match="project shot contract"):
        await sdk.generate_video_plan()


@pytest.mark.asyncio
async def test_h3_output_validation_uses_valid_frame_duration(session):
    media = await create_media_item(session, file_format="mp4", tool_id="comfyui:minimax_h3_r2v", duration=158 / 24)
    assert await validate_shot_output(session, contract={"expected_duration": 6}, media_id=media.id) == []
    media.duration = 6
    assert await validate_shot_output(session, contract={"expected_duration": 6}, media_id=media.id)


@pytest.mark.asyncio
async def test_chat_settings_route_preserves_plan_and_rejects_forged_reviews(session, test_chat, monkeypatch):
    from routes.chats import update_chat, ChatUpdateRequest

    monkeypatch.setattr("routes.chats.ws_manager", SimpleNamespace(broadcast=AsyncMock()))
    plan = normalize_plan(draft())
    test_chat.generation_settings = json.dumps({"_video_plan": plan, "video_duration": 5})
    await session.commit()
    result = await update_chat(test_chat.id, ChatUpdateRequest(generation_settings='{"video_duration":6,"_video_plan":{"approved_media_ids":[1]}}'), session)
    assert result.generation_settings["_video_plan"] == plan
    assert result.generation_settings["video_duration"] == 6


@pytest.mark.asyncio
async def test_real_dispatch_blocks_before_queue_and_records_effective_timing(session, tmp_path, monkeypatch):
    import agent.v2.tools.call_tool as ct

    path = tmp_path / "reference.png"
    path.write_bytes(b"reference")
    media = await create_media_item(session, file_path=path)
    plan = normalize_plan(draft(media.id), controls={"fast": False, "steps": 20, "resolution": "720"})
    settings = {"_video_plan": plan, "video_duration": 6}
    descriptor = SimpleNamespace(name="H3", task_types=["image-to-video"], task_type="image-to-video", subtitle="", parameter_schema={"properties": {"prompt": {}, "input_images": {}, "duration": {}, "steps": {}}})
    provider = SimpleNamespace(provider_id="comfyui", provider_type="external")
    monkeypatch.setattr(ct.ProviderRegistry, "get_instance", lambda: SimpleNamespace(get_tool=lambda _: (provider, descriptor)))
    queue = SimpleNamespace(submit_job=AsyncMock(side_effect=RuntimeError("__queued__")))
    monkeypatch.setattr(ct, "get_generation_queue", lambda: queue)
    monkeypatch.setattr(ct, "_get_default_folder", lambda _: str(tmp_path))
    settings_session = SimpleNamespace(get=AsyncMock(side_effect=lambda *args: SimpleNamespace(generation_settings=json.dumps(settings))))

    class SettingsContext:
        async def __aenter__(self):
            return settings_session

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr("database_registry.get_database_registry", lambda: SimpleNamespace(get_database=lambda _: SimpleNamespace(async_session_maker=SettingsContext)))
    clip = plan["clips"][0]
    kwargs = {"tool_id": clip["tool_id"], "parameters": clip["parameters"], "session": session, "chat_id": 99, "video_plan_clip": clip["id"], "video_plan_key": plan_key(plan)}
    with pytest.raises(ValueError, match="Review"):
        await ct.execute_call_tool(**kwargs)
    queue.submit_job.assert_not_awaited()
    approve(settings, {"media_ids": [media.id]})
    with pytest.raises(ValueError, match="explicitly start"):
        await ct.execute_call_tool(**kwargs)
    queue.submit_job.assert_not_awaited()
    approve(settings, {"start": True})
    settings["video_duration"] = 5
    with pytest.raises(ValueError, match="differs"):
        await ct.execute_call_tool(**kwargs)
    queue.submit_job.assert_not_awaited()
    settings["video_duration"] = 6
    with pytest.raises(RuntimeError, match="__queued__"):
        await ct.execute_call_tool(**kwargs)
    params = queue.submit_job.await_args.kwargs["parameters"]
    assert params["duration"] == params["prompt_metadata"]["video_duration"] == 6
    assert params["prompt_metadata"]["frame_count"] == 158
    assert params["prompt_metadata"]["effective_duration"] == 158 / 24
    assert "_modal_video_sequence" not in params
    with pytest.raises(RuntimeError, match="__queued__"):
        await ct.execute_call_tool(**kwargs, video_sequence_id="f" * 32)
    assert queue.submit_job.await_args.kwargs["parameters"]["_modal_video_sequence"] == "f" * 32
