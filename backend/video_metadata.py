"""Embed Stimma generation provenance in video container metadata.

Generated images already carry their provenance in PNG/EXIF fields.  Videos
are containers, so their equivalent is the MP4/WebM format metadata.  Keep the
payload JSON-shaped and portable: players that understand only standard tags
can still show the title/description, while Stimma can recover the complete
generation record from ``comment`` or ``description``.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional


log = logging.getLogger(__name__)

VIDEO_SUFFIXES = frozenset({".mp4", ".webm", ".mov", ".mkv", ".avi"})
VIDEO_METADATA_VERSION = 1


def infer_workflow_type(generation_metadata: dict[str, Any]) -> str:
    """Return a compact workflow family such as ``T2V``, ``I2V`` or ``R2V``."""
    task_type = str(generation_metadata.get("task_type") or "").lower()
    tool_id = str(generation_metadata.get("tool_id") or "").lower()
    haystack = f"{tool_id} {task_type}"

    # Check the more specific reference/video variants first.  This also
    # handles MiniMax's ``ref2va`` naming and Stimma's reference-to-video task.
    if any(token in haystack for token in ("r2v", "ref2va", "reference-to-video")):
        return "R2V"
    if any(token in haystack for token in ("i2v", "fl2va", "image-to-video")):
        return "I2V"
    if any(token in haystack for token in ("t2v", "text-to-video")):
        return "T2V"
    if "video-to-video" in haystack or "v2v" in haystack:
        return "V2V"
    if "video-extend" in haystack or "extend" in haystack:
        return "EXTEND"
    if "video-stitch" in haystack or "stitch" in haystack:
        return "STITCH"
    if "upscale-video" in haystack or "video-upscale" in haystack:
        return "UPSCALE"
    return str(generation_metadata.get("task_type") or "VIDEO").upper()


def quality_label(width: int, height: int) -> str:
    """Map actual output dimensions to the requested human-friendly tier.

    The long edge identifies 2K landscape/portrait outputs (2048x1080 and
    2560x1440, for example), while the short edge distinguishes 480p, 720p,
    and 1080p.  This avoids labelling the common 768x1344 H3 canvas as 1080p.
    """
    width = int(width or 0)
    height = int(height or 0)
    if width <= 0 or height <= 0:
        return "unknown"

    long_edge = max(width, height)
    short_edge = min(width, height)
    if long_edge >= 2000:
        return "2K"
    if short_edge <= 540:
        return "480p"
    if short_edge <= 900:
        return "720p"
    if short_edge <= 1440:
        return "1080p"
    return f"{short_edge}p"


def _parse_rate(value: Any) -> Optional[float]:
    if not value:
        return None
    try:
        if isinstance(value, str) and "/" in value:
            numerator, denominator = value.split("/", 1)
            denominator_float = float(denominator)
            return float(numerator) / denominator_float if denominator_float else None
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _probe_video(path: Path) -> dict[str, Any]:
    """Return the actual encoded dimensions/fps/duration when ffprobe exists."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries",
                "stream=width,height,r_frame_rate,avg_frame_rate,duration:format=duration",
                "-of", "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            return {}
        payload = json.loads(result.stdout or "{}")
        stream = (payload.get("streams") or [{}])[0]
        fmt = payload.get("format") or {}
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        duration = stream.get("duration") or fmt.get("duration")
        fps = _parse_rate(stream.get("avg_frame_rate") or stream.get("r_frame_rate"))
        return {
            "width": width,
            "height": height,
            "fps": fps,
            "duration": float(duration) if duration not in (None, "N/A") else None,
        }
    except (OSError, TypeError, ValueError, subprocess.TimeoutExpired):
        return {}


def _video_metadata_dict(
    generation_metadata: str,
    *,
    width: int,
    height: int,
    fps: Optional[float] = None,
    duration: Optional[float] = None,
) -> tuple[str, dict[str, Any]]:
    """Enrich canonical generation metadata and return its compact JSON form."""
    try:
        metadata = json.loads(generation_metadata)
    except (TypeError, ValueError):
        return generation_metadata, {}
    if not isinstance(metadata, dict):
        return generation_metadata, {}

    # ffprobe is normally available in the generation runtime.  Keep a useful
    # requested-resolution fallback for unusual containers where it cannot read
    # the stream, while preferring the actual encoded dimensions whenever known.
    params_from_metadata = metadata.get("parameters") or {}
    if not isinstance(params_from_metadata, dict):
        params_from_metadata = {}
    if not width:
        try:
            width = int(params_from_metadata.get("width") or 0)
        except (TypeError, ValueError):
            width = 0
    if not height:
        try:
            height = int(params_from_metadata.get("height") or 0)
        except (TypeError, ValueError):
            height = 0

    workflow_type = infer_workflow_type(metadata)
    quality = quality_label(width, height)
    video = {
        "width": int(width or 0),
        "height": int(height or 0),
        "resolution": f"{int(width)}x{int(height)}" if width and height else None,
        "quality": quality,
    }
    if fps is not None:
        video["fps"] = round(float(fps), 3)
    if duration is not None:
        video["duration"] = round(float(duration), 3)
    video = {key: value for key, value in video.items() if value is not None}

    # Keep the canonical record intact and add stable, discoverable fields.
    # Existing consumers use the canonical keys and safely ignore these extras.
    metadata["video_metadata_version"] = VIDEO_METADATA_VERSION
    metadata["workflow_type"] = workflow_type
    metadata["workflow_id"] = metadata.get("tool_id")
    metadata["quality"] = quality
    metadata["resolution"] = video.get("resolution")
    metadata["video"] = video
    params = metadata.get("parameters") or {}
    if not isinstance(params, dict):
        params = {}
    else:
        params = dict(params)
    params.setdefault("output_width", int(width or 0))
    params.setdefault("output_height", int(height or 0))
    params["output_quality"] = quality
    metadata["parameters"] = params

    encoded = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
    return encoded, metadata


def embed_video_generation_metadata(
    output_path: str | Path,
    generation_metadata: str,
) -> str:
    """Remux a generated video with provenance tags and return enriched JSON.

    The video and audio streams are copied losslessly.  If ffmpeg is missing or
    the source cannot be remuxed, the enriched JSON is still returned so the
    library keeps the same metadata even though the file tag could not be
    written.
    """
    path = Path(output_path)
    if path.suffix.lower() not in VIDEO_SUFFIXES or not path.is_file():
        return generation_metadata

    probed = _probe_video(path)
    encoded, metadata = _video_metadata_dict(
        generation_metadata,
        width=int(probed.get("width") or 0),
        height=int(probed.get("height") or 0),
        fps=probed.get("fps"),
        duration=probed.get("duration"),
    )
    if not metadata:
        return generation_metadata

    workflow_type = str(metadata.get("workflow_type") or "VIDEO")
    quality = str(metadata.get("quality") or "unknown")
    resolution = str(metadata.get("resolution") or "unknown")
    title = f"Stimma — {workflow_type} — {quality} — {resolution}"

    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{path.stem}.",
            suffix=path.suffix,
            dir=path.parent,
            delete=False,
        ) as temp_file:
            temp_name = temp_file.name

        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(path),
            "-map", "0",
            "-c", "copy",
            "-metadata", f"title={title}",
            "-metadata", "artist=Stimma",
            # Both are standard container tags.  Some players expose only
            # description, while ffprobe and Stimma prefer comment.
            "-metadata", f"comment={encoded}",
            "-metadata", f"description={encoded}",
            temp_name,
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            log.warning("Could not embed video metadata in %s: %s", path, result.stderr[-1000:])
            return encoded
        os.replace(temp_name, path)
        temp_name = None
        return encoded
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("Could not embed video metadata in %s: %s", path, exc)
        return encoded
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass
