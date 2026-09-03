"""Tests for timestamped video storyboards sent to the agent vision context."""

import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from agent.v2.conversation import _build_view_image_result
from agent.v2.tools import view_video as view_video_module
from agent.v2.tools.view_video import MAX_FRAME_COUNT, view_video
from agent.v2.tools_registry import get_tool


def _fake_probe(_path):
    return {"duration": 10.0, "fps": 24.0, "width": 640, "height": 360}


def _fake_extract(_path, position="custom", time_seconds=None):
    assert position == "custom"
    timestamp = float(time_seconds or 0.0)
    color = (int(timestamp * 20) % 255, 80, 160)
    return Image.new("RGB", (640, 360), color), timestamp, 10.0, 24.0


@pytest.mark.asyncio
async def test_view_video_builds_timestamped_storyboard(tmp_path, monkeypatch):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"test video placeholder")
    monkeypatch.setattr(view_video_module, "probe_video_stream_info", _fake_probe)
    monkeypatch.setattr(view_video_module, "extract_frame_to_image", _fake_extract)
    monkeypatch.setattr(
        view_video_module,
        "get_ffmpeg_checker",
        lambda: type(
            "Checker",
            (),
            {
                "check_availability": staticmethod(lambda: (True, True)),
                "get_install_instructions": staticmethod(lambda: "install ffmpeg"),
            },
        )(),
    )

    result = await view_video(
        path=video_path.name,
        frame_count=6,
        detail="high",
        workspace_dir=str(tmp_path),
    )
    marker = json.loads(result)

    assert marker["__view_image__"] is True
    assert marker["view_kind"] == "video_storyboard"
    assert marker["source_path"] == str(video_path)
    assert marker["frame_count"] == 6
    assert len(marker["frame_times"]) == 6
    assert marker["frame_times"][0] == 0.0
    assert marker["frame_times"][-1] == pytest.approx(10.0 - 1.0 / 24.0, abs=1e-4)
    assert max(marker["size"]) <= 1024
    assert Path(marker["path"]).is_file()

    built = _build_view_image_result("tool-1", marker)
    text_block = next(block for block in built["content"] if block["type"] == "text")
    assert "Video storyboard loaded for clip.mp4" in text_block["text"]
    assert "6 frames sampled" in text_block["text"]
    assert "Audio was not analyzed" in text_block["text"]
    image_block = next(block for block in built["content"] if block["type"] == "image_url")
    encoded = image_block["image_url"]["url"].split(",", 1)[1]
    assert base64.b64decode(encoded).startswith(b"\xff\xd8")


@pytest.mark.asyncio
async def test_view_video_clamps_frame_count(tmp_path, monkeypatch):
    video_path = tmp_path / "clip.webm"
    video_path.write_bytes(b"test video placeholder")
    calls = []

    def tracked_extract(*args, **kwargs):
        calls.append(kwargs.get("time_seconds"))
        return _fake_extract(*args, **kwargs)

    monkeypatch.setattr(view_video_module, "probe_video_stream_info", _fake_probe)
    monkeypatch.setattr(view_video_module, "extract_frame_to_image", tracked_extract)
    monkeypatch.setattr(
        view_video_module,
        "get_ffmpeg_checker",
        lambda: type(
            "Checker",
            (),
            {
                "check_availability": staticmethod(lambda: (True, True)),
                "get_install_instructions": staticmethod(lambda: "install ffmpeg"),
            },
        )(),
    )

    marker = json.loads(
        await view_video(path=str(video_path), frame_count=999, detail="low")
    )

    assert marker["frame_count"] == MAX_FRAME_COUNT
    assert len(calls) == MAX_FRAME_COUNT
    assert max(marker["size"]) <= 512


@pytest.mark.asyncio
async def test_view_video_rejects_non_video_path(tmp_path):
    image_path = tmp_path / "still.png"
    Image.new("RGB", (16, 16), "red").save(image_path)

    result = await view_video(path=str(image_path))

    assert result == "Error: Unsupported video format: .png"


@pytest.mark.asyncio
async def test_view_video_rejects_invalid_detail_before_decoding(tmp_path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"test video placeholder")

    result = await view_video(path=str(video_path), detail="original")

    assert result == "Error: detail must be 'low' or 'high'"


def test_view_video_is_registered_for_agent_and_flow_scopes():
    registered = get_tool("view_video")

    assert registered is not None
    assert registered.visible_in("agent") is True
    assert registered.visible_in("flow") is True
    assert "does not analyze audio" in registered.description


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)
@pytest.mark.asyncio
async def test_view_video_decodes_a_real_mp4(tmp_path):
    video_path = tmp_path / "real.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=160x90:rate=12:duration=1",
            str(video_path),
        ],
        check=True,
        capture_output=True,
    )

    marker = json.loads(
        await view_video(path=str(video_path), frame_count=4, detail="low")
    )

    assert marker["view_kind"] == "video_storyboard"
    assert marker["frame_count"] == 4
    assert marker["video_info"]["width"] == 160
    assert marker["video_info"]["height"] == 90
    assert marker["video_info"]["duration"] == pytest.approx(1.0, abs=0.1)
    assert Path(marker["path"]).is_file()
