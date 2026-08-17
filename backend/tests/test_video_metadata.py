"""Video container provenance metadata tests."""

import json
import shutil
import subprocess

import pytest

from video_metadata import embed_video_generation_metadata, infer_workflow_type, quality_label


@pytest.mark.parametrize(
    ("task_type", "tool_id", "expected"),
    [
        ("text-to-video", "comfyui:minimax-h3-t2v-turbo", "T2V"),
        ("image-to-video", "comfyui:minimax-h3-i2v", "I2V"),
        ("reference-to-video", "comfyui:minimax-h3-r2v", "R2V"),
    ],
)
def test_infer_workflow_type(task_type, tool_id, expected):
    assert infer_workflow_type({"task_type": task_type, "tool_id": tool_id}) == expected


@pytest.mark.parametrize(
    ("width", "height", "expected"),
    [
        (854, 480, "480p"),
        (1280, 720, "720p"),
        (1920, 1080, "1080p"),
        (2048, 1080, "2K"),
        (2560, 1440, "2K"),
    ],
)
def test_quality_label(width, height, expected):
    assert quality_label(width, height) == expected


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)
def test_embed_video_generation_metadata_round_trip(tmp_path):
    video_path = tmp_path / "generated.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=1280x720:d=0.2:r=24",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video_path),
        ],
        check=True,
    )
    source_metadata = {
        "version": 3,
        "source": "stimma",
        "task_type": "image-to-video",
        "tool_id": "comfyui:minimax-h3-i2v-turbo",
        "generator": "comfyui",
        "model": "MiniMax H3",
        "prompt": "a test",
        "negative_prompt": "",
        "parameters": {"steps": 4, "seed": 42},
        "prompt_metadata": None,
        "source_inputs": [],
        "lineage_trace": [],
        "generated_at": "2026-08-17T00:00:00Z",
    }

    enriched = json.loads(
        embed_video_generation_metadata(video_path, json.dumps(source_metadata))
    )
    assert enriched["workflow_type"] == "I2V"
    assert enriched["quality"] == "720p"
    assert enriched["resolution"] == "1280x720"
    assert enriched["parameters"]["steps"] == 4

    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format_tags", "-of", "json", str(video_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    tags = (json.loads(probe.stdout).get("format") or {}).get("tags") or {}
    embedded = json.loads(tags["comment"])
    assert embedded["workflow_type"] == "I2V"
    assert embedded["quality"] == "720p"
    assert embedded["parameters"]["seed"] == 42

