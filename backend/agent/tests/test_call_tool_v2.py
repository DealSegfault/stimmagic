import json
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from database import ChatItem, MediaItem

from agent.v2.tools.call_tool import (
    _r2v_variant_tool_id,
    _chat_reference_videos,
    _inject_chat_reference_videos,
    _normalize_misclassified_video_inputs,
    _resolve_effective_task_type,
    _select_h3_generation_prompt,
    _wait_timeout_for_task_type,
    call_tool,
    execute_call_tool,
)
from h3_prompt_pair import format_h3_prompt_pair


def _write_video(path: Path, content: bytes = b"fake") -> str:
    path.write_bytes(content)
    return str(path)


class _FakeToolDescriptor:
    def __init__(self):
        self.id = "image:model-a"
        self.name = "Model A"
        self.task_type = "text-to-image"
        self.task_types = ["text-to-image", "image-to-image"]
        self.parameter_schema = {
            "properties": {
                "prompt": {"type": "string"},
                "input_images": {"type": "array"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
            },
            "required": ["prompt"],
        }
        self.default_width = 1024
        self.default_height = 1024


@pytest.fixture
def fake_provider():
    provider = MagicMock()
    provider.provider_id = "test-provider"
    return provider


@pytest.fixture
def fake_descriptor():
    return _FakeToolDescriptor()


@pytest.fixture
def fake_queue():
    queue = MagicMock()
    queue.submit_job = AsyncMock(return_value=42)
    queue._resolve_backend_info = MagicMock(return_value=("test-backend", None))
    return queue


@pytest.fixture
def mock_generation(monkeypatch, fake_queue, fake_provider, fake_descriptor):
    """Mock the generation pipeline: registry, queue, and wait_for_jobs."""
    registry = MagicMock()
    registry.get_tool.return_value = (fake_provider, fake_descriptor)

    monkeypatch.setattr(
        "agent.v2.tools.call_tool.ProviderRegistry.get_instance",
        lambda: registry,
    )
    monkeypatch.setattr(
        "agent.v2.tools.call_tool.get_generation_queue",
        lambda: fake_queue,
    )

    async def fake_wait(job_ids, session, **kwargs):
        return [555], [], 0, {42: 555}

    monkeypatch.setattr(
        "agent.v2.tools.call_tool.wait_for_jobs",
        fake_wait,
    )

    # Mock the database lookup for media file path (imported inside function body)
    monkeypatch.setattr(
        "database_registry.get_database_registry",
        lambda: MagicMock(
            get_database=lambda pid: MagicMock(
                async_session_maker=MagicMock(
                    return_value=_FakeSessionContext("/tmp/test_output.png")
                )
            )
        ),
    )
    monkeypatch.setattr(
        "agent.v2.tools.call_tool.get_current_profile",
        lambda: "test-profile",
    )
    monkeypatch.setattr(
        "agent.v2.tools.call_tool._get_default_folder",
        lambda _=None: "/tmp/output",
    )

    return registry


class _FakeSessionContext:
    """Async context manager that returns a fake session for media lookup."""

    def __init__(self, file_path):
        self._file_path = file_path

    async def __aenter__(self):
        session = MagicMock()
        session.get = AsyncMock(return_value=None)
        result = MagicMock()
        result.one_or_none.return_value = (self._file_path, 1024, 1024)
        session.execute = AsyncMock(return_value=result)
        return session

    async def __aexit__(self, *args):
        pass


@pytest.mark.asyncio
async def test_call_tool_routes_input_images(session, test_chat, fake_queue, mock_generation, tmp_path):
    result = await call_tool(
        tool_id="image:model-a",
        parameters={"prompt": "a cat", "input_images": [101]},
        session=session,
        chat_id=test_chat.id,
        workspace_dir=str(tmp_path),
        interrupt_checker=lambda: False,
    )

    assert "media_id=555" in result
    assert "Not yet shown to the user" in result
    assert fake_queue.submit_job.called
    submit_kwargs = fake_queue.submit_job.call_args
    assert submit_kwargs.kwargs["task_type"] == "image-to-image"
    assert submit_kwargs.kwargs["parameters"]["input_images"] == [101]
    assert submit_kwargs.kwargs["parameters"]["input_media_ids"] == [101]


def test_resolve_effective_task_type_routes_input_videos():
    descriptor = _FakeToolDescriptor()
    descriptor.task_type = "text-to-video"
    descriptor.task_types = ["text-to-video", "video-to-video"]

    assert _resolve_effective_task_type(descriptor, {"input_videos": [202]}) == "video-to-video"


def test_video_jobs_use_extended_stall_timeout():
    """Long H3 renders must not be reported as stalled at the generic 30m limit."""
    assert _wait_timeout_for_task_type("reference-to-video") == 3600.0
    assert _wait_timeout_for_task_type("text-to-image") is None


def test_h3_video_reference_promotes_i2v_or_t2v_to_r2v():
    assert _r2v_variant_tool_id("comfyui:minimax-h3-i2v") == "comfyui:minimax-h3-r2v"
    assert _r2v_variant_tool_id("comfyui:minimax_h3_t2v_turbo") == "comfyui:minimax_h3_r2v_turbo"
    assert _r2v_variant_tool_id("comfyui:wan-i2v") is None


@pytest.mark.asyncio
async def test_h3_video_dispatch_selects_chinese_from_prompt_envelope():
    english = "integrated_multimodal_description: [Shot 1] Maya waits."
    chinese = "integrated_multimodal_description: [Shot 1] Maya保持等待。"

    selected, pair = await _select_h3_generation_prompt(
        format_h3_prompt_pair(english, chinese),
        task_type="reference-to-video",
        session=object(),
        chat_id=None,
    )

    assert selected == chinese
    assert pair == {"english": english, "chinese": chinese}


@pytest.mark.asyncio
async def test_explicit_reference_task_does_not_fall_back_to_i2v(
    session, fake_provider, fake_descriptor, monkeypatch
):
    """A mismatched Ref2VA binding must fail before submitting an I2V job."""
    registry = MagicMock()
    registry.get_tool.return_value = (fake_provider, fake_descriptor)
    monkeypatch.setattr(
        "agent.v2.tools.call_tool.ProviderRegistry.get_instance",
        lambda: registry,
    )

    with pytest.raises(ValueError, match="explicitly requested task type 'reference-to-video'"):
        await execute_call_tool(
            tool_id="comfyui:minimax-h3-r2v-turbo",
            parameters={"prompt": "two references", "input_images": [1, 2]},
            task_type_override="reference-to-video",
            session=session,
        )


@pytest.mark.asyncio
async def test_chat_reference_videos_includes_all_user_messages_and_selected_media_ids(
    session,
    test_chat,
    tmp_path,
):
    old_video = _write_video(tmp_path / "old.mp4")
    latest_video = _write_video(tmp_path / "latest.mp4")
    selected_video = _write_video(tmp_path / "selected.mp4")

    media_item = MediaItem(
        file_path=selected_video,
        file_hash="hash",
        file_size=4,
        file_format="mp4",
        width=16,
        height=16,
        megapixels=0.000256,
    )
    session.add(media_item)
    await session.flush()

    session.add(ChatItem(
        chat_id=test_chat.id,
        item_type="user_message",
        message_text="old reference",
        item_metadata=json.dumps({
            "workspace_files": [
                {
                    "media_type": "video",
                    "media_id": 111,
                    "path": old_video,
                    "filename": "old.mp4",
                }
            ],
        }),
    ))
    session.add(ChatItem(
        chat_id=test_chat.id,
        item_type="user_message",
        message_text="latest reference",
        item_metadata=json.dumps({
            "attachments": [
                {
                    "media_type": "video",
                    "media_id": 222,
                    "path": latest_video,
                    "filename": "latest.mp4",
                }
            ],
            "selected_media_ids": [media_item.id],
        }),
    ))
    await session.commit()

    refs = await _chat_reference_videos(test_chat.id, session, str(tmp_path))
    paths = [item["path"] for item in refs]

    assert paths == [old_video, latest_video, selected_video]


@pytest.mark.asyncio
async def test_video_accidentally_passed_as_image_is_moved_to_typed_video_input(
    session,
    session_factory,
    monkeypatch,
    tmp_path,
):
    still = tmp_path / "character.png"
    still.write_bytes(b"fake image")
    video = tmp_path / "clay.mp4"
    video.write_bytes(b"fake video")

    video_item = MediaItem(
        file_path=str(video),
        file_hash="video-hash",
        file_size=10,
        file_format="mp4",
        width=16,
        height=16,
        megapixels=0.000256,
    )
    session.add(video_item)
    await session.commit()

    class _Database:
        async_session_maker = session_factory

    class _DatabaseRegistry:
        @staticmethod
        def get_database(_profile):
            return _Database()

    monkeypatch.setattr(
        "database_registry.get_database_registry",
        lambda: _DatabaseRegistry(),
    )

    params = {
        "input_images": [str(still), f"media:{video_item.id}"],
        "input_media_ids": [999, video_item.id],
    }
    moved = await _normalize_misclassified_video_inputs(params, session, str(tmp_path))

    assert moved is True
    assert params["input_images"] == [str(still)]
    assert params["input_media_ids"] == [999]
    assert params["input_videos"] == [video_item.id]
    assert params["input_video_media_ids"] == [video_item.id]


@pytest.mark.asyncio
async def test_chat_video_injection_keeps_video_media_ids_positional(monkeypatch, session):
    monkeypatch.setattr(
        "agent.v2.tools.call_tool._chat_reference_videos",
        AsyncMock(return_value=[{"path": "/tmp/reference.mp4", "media_id": 222}]),
    )
    params = {"input_videos": ["/tmp/already-present.mp4"]}

    await _inject_chat_reference_videos(params, 1, session, None)

    assert params["input_videos"] == ["/tmp/already-present.mp4", "/tmp/reference.mp4"]
    assert params["input_video_media_ids"] == [None, 222]
