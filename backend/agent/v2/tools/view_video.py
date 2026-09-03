"""View a video as a timestamped storyboard for multimodal reasoning."""

from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from core.logging import get_logger
from ffmpeg_checker import get_ffmpeg_checker
from utils.video_frames import extract_frame_to_image, probe_video_stream_info

from ..tools_registry import ToolParameter, tool
from ..vision_payload import write_agent_jpeg


log = get_logger(__name__)

MAX_LOW = 512
MAX_HIGH = 1024
DEFAULT_FRAME_COUNT = 8
MIN_FRAME_COUNT = 2
MAX_FRAME_COUNT = 12
VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
    ".m4v",
    ".mpg",
    ".mpeg",
}


def _load_font(size: int) -> ImageFont.ImageFont:
    """Load a readable cross-platform font, falling back to Pillow's default."""
    candidates = (
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    )
    for candidate in candidates:
        if not Path(candidate).exists():
            continue
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _format_timestamp(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    minutes = int(seconds // 60)
    remainder = seconds - minutes * 60
    return f"{minutes:02d}:{remainder:05.2f}"


def _sample_times(duration: float, fps: float, count: int) -> list[float]:
    """Return evenly distributed timestamps including the opening and final frame."""
    if duration <= 0:
        return [0.0]
    frame_backoff = 1.0 / fps if fps > 0 else 0.05
    final_time = max(0.0, duration - frame_backoff)
    if count <= 1 or final_time <= 0:
        return [0.0]
    return [final_time * index / (count - 1) for index in range(count)]


def _compose_storyboard(
    frames: list[Image.Image],
    times: list[float],
    *,
    max_side: int,
    title: str,
    video_info: dict[str, Any],
) -> Image.Image:
    """Compose full-frame, timestamped tiles into one bounded vision payload."""
    count = len(frames)
    columns = min(4, count)
    rows = math.ceil(count / columns)
    gap = max(5, max_side // 128)
    label_height = max(16, max_side // 48)
    header_height = max(24, max_side // 32)
    cell_width = max(32, (max_side - gap * (columns + 1)) // columns)

    available_frame_height = (
        max_side
        - header_height
        - rows * label_height
        - gap * (rows + 3)
    )
    frame_height_limit = max(32, available_frame_height // rows)
    first = frames[0]
    natural_height = round(cell_width * first.height / max(1, first.width))
    frame_height = max(32, min(frame_height_limit, natural_height))

    sheet_height = (
        gap
        + header_height
        + gap
        + rows * (frame_height + label_height)
        + (rows - 1) * gap
        + gap
    )
    sheet = Image.new("RGB", (max_side, min(max_side, sheet_height)), (10, 13, 18))
    draw = ImageDraw.Draw(sheet)
    header_font = _load_font(max(12, max_side // 52))
    label_font = _load_font(max(10, max_side // 68))

    duration = float(video_info.get("duration") or 0.0)
    fps = float(video_info.get("fps") or 0.0)
    dimensions = f"{video_info.get('width') or '?'}x{video_info.get('height') or '?'}"
    safe_title = title if len(title) <= 48 else f"{title[:45]}..."
    header = f"{safe_title}  |  {duration:.2f}s  |  {fps:.2f} fps  |  {dimensions}"
    draw.text((gap, gap), header, fill=(225, 231, 239), font=header_font)

    grid_y = gap + header_height + gap
    for index, (frame, timestamp) in enumerate(zip(frames, times)):
        row, column = divmod(index, columns)
        x = gap + column * (cell_width + gap)
        y = grid_y + row * (frame_height + label_height + gap)

        tile = Image.new("RGB", (cell_width, frame_height), (2, 4, 8))
        fitted = ImageOps.contain(
            frame.convert("RGB"),
            (cell_width, frame_height),
            method=Image.Resampling.LANCZOS,
        )
        tile.paste(
            fitted,
            ((cell_width - fitted.width) // 2, (frame_height - fitted.height) // 2),
        )
        sheet.paste(tile, (x, y))
        draw.text(
            (x, y + frame_height + 2),
            f"#{index + 1}  {_format_timestamp(timestamp)}",
            fill=(176, 188, 204),
            font=label_font,
        )

    return sheet


def _decode_storyboard(
    video_path: Path,
    *,
    frame_count: int,
    max_side: int,
) -> tuple[Image.Image, dict[str, Any], list[float]]:
    """Probe, sample, and compose a video without blocking the async agent loop."""
    checker = get_ffmpeg_checker()
    ffmpeg_available, ffprobe_available = checker.check_availability()
    if not ffmpeg_available or not ffprobe_available:
        missing = [
            name
            for name, available in (
                ("ffmpeg", ffmpeg_available),
                ("ffprobe", ffprobe_available),
            )
            if not available
        ]
        raise RuntimeError(
            f"Missing {', '.join(missing)}. "
            f"{checker.get_install_instructions()}"
        )

    video_info = probe_video_stream_info(video_path)
    requested_times = _sample_times(
        float(video_info.get("duration") or 0.0),
        float(video_info.get("fps") or 0.0),
        frame_count,
    )

    frames: list[Image.Image] = []
    actual_times: list[float] = []
    for requested_time in requested_times:
        try:
            frame, actual_time, duration, fps = extract_frame_to_image(
                video_path,
                position="custom",
                time_seconds=requested_time,
            )
        except Exception as exc:
            log.warning(
                "view_video frame decode failed",
                video_path=str(video_path),
                timestamp=requested_time,
                error=str(exc),
            )
            continue
        frames.append(frame.copy())
        frame.close()
        actual_times.append(actual_time)
        if not video_info.get("duration") and duration:
            video_info["duration"] = duration
        if not video_info.get("fps") and fps:
            video_info["fps"] = fps
        if not video_info.get("width") or not video_info.get("height"):
            video_info["width"], video_info["height"] = frames[-1].size

    if not frames:
        raise ValueError("Could not decode any visual frames from this video.")

    try:
        storyboard = _compose_storyboard(
            frames,
            actual_times,
            max_side=max_side,
            title=video_path.name,
            video_info=video_info,
        )
    finally:
        for frame in frames:
            frame.close()
    return storyboard, video_info, actual_times


@tool(
    name="view_video",
    description=(
        "Inspect a video's visual content. Extracts a bounded, timestamped storyboard "
        "with evenly sampled frames and sends that single image into your context. "
        "Use this for visual review of MP4/MOV/WebM and other videos; use media_info "
        "for generation parameters. This tool reviews frames only and does not analyze audio."
    ),
    parameters=[
        ToolParameter(
            name="media_id",
            type="integer",
            description="Video media ID to inspect (alternative to path)",
            required=False,
        ),
        ToolParameter(
            name="path",
            type="string",
            description="Video path, relative to the workspace or absolute (alternative to media_id)",
            required=False,
        ),
        ToolParameter(
            name="frame_count",
            type="integer",
            description="Number of evenly sampled frames; clamped to 2-12 (default 8)",
            required=False,
        ),
        ToolParameter(
            name="detail",
            type="string",
            description="Storyboard resolution: 'low' (512px) or 'high' (1024px, default)",
            required=False,
            enum=["low", "high"],
        ),
    ],
    scope="both",
)
async def view_video(
    path: str | None = None,
    media_id: int | None = None,
    frame_count: int = DEFAULT_FRAME_COUNT,
    detail: str = "high",
    **kwargs,
) -> str:
    workspace_dir = kwargs.get("workspace_dir")
    session = kwargs.get("session")

    media_item = None
    if media_id is not None and session:
        from database import MediaItem
        from sqlalchemy import select

        result = await session.execute(select(MediaItem).where(MediaItem.id == media_id))
        media_item = result.scalar_one_or_none()
        if (
            not media_item
            or not media_item.file_path
            or media_item.deleted_at is not None
            or media_item.deletion_pending_at is not None
        ):
            return f"Error: Media {media_id} not found"
        resolved = Path(media_item.file_path)
        media_format = str(media_item.file_format or "").lower().lstrip(".")
        if media_format and f".{media_format}" not in VIDEO_EXTENSIONS:
            return f"Error: Media {media_id} is not a supported video"
    elif path:
        resolved = Path(path)
        if not resolved.is_absolute() and workspace_dir:
            resolved = Path(workspace_dir) / path
        if resolved.suffix and resolved.suffix.lower() not in VIDEO_EXTENSIONS:
            return f"Error: Unsupported video format: {resolved.suffix.lower()}"
    else:
        return "Error: Provide either path or media_id"

    if not resolved.exists():
        return f"Error: File not found: {resolved}"

    try:
        requested_count = int(frame_count)
    except (TypeError, ValueError):
        return "Error: frame_count must be an integer"
    if detail not in {"low", "high"}:
        return "Error: detail must be 'low' or 'high'"
    bounded_count = max(MIN_FRAME_COUNT, min(MAX_FRAME_COUNT, requested_count))
    max_side = MAX_LOW if detail == "low" else MAX_HIGH

    try:
        storyboard, video_info, actual_times = await asyncio.to_thread(
            _decode_storyboard,
            resolved,
            frame_count=bounded_count,
            max_side=max_side,
        )
        try:
            snapshot_path = write_agent_jpeg(storyboard)
            width, height = storyboard.size
        finally:
            storyboard.close()
    except Exception as exc:
        log.error(f"view_video failed for {resolved}: {exc}")
        return f"Error analyzing video: {exc}"

    marker = {
        "__view_image__": True,
        "view_kind": "video_storyboard",
        "path": str(snapshot_path),
        "source_path": str(resolved),
        "size": [width, height],
        "native_size": [width, height],
        "detail": detail,
        "media_type": "image/jpeg",
        "video_info": {
            "duration": round(float(video_info.get("duration") or 0.0), 4),
            "fps": round(float(video_info.get("fps") or 0.0), 4),
            "width": int(video_info.get("width") or 0),
            "height": int(video_info.get("height") or 0),
        },
        "frame_times": [round(timestamp, 4) for timestamp in actual_times],
        "frame_count": len(actual_times),
    }
    return json.dumps(marker)
