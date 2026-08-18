"""Chat-level video generation preferences.

The chat controls are intentionally resolved at dispatch time.  The model may
choose a valid H3 tool and provide its own defaults, but these preferences are
the user's authoritative overrides for video jobs.
"""

from __future__ import annotations

from math import isfinite
from typing import Any, Mapping, Optional, Sequence


VIDEO_DEFAULT_STEPS = 20
VIDEO_DEFAULT_RESOLUTION = "720"
VIDEO_DEFAULT_DURATION = 5.0
VIDEO_FAST_STEPS = 8

# Resolution is expressed as the requested short edge.  H3's native canvas or
# a provider's x-allowed-dimensions can clamp the final pair when necessary.
VIDEO_RESOLUTION_SHORT_EDGES = {
    "480": 480,
    "720": 720,
    "1080": 1080,
    "2k": 1440,
}


def _as_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def normalize_video_chat_settings(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return safe, bounded values from a chat's JSON settings blob."""

    settings = settings if isinstance(settings, Mapping) else {}
    nested = settings.get("video_settings")
    if not isinstance(nested, Mapping):
        nested = {}

    raw_steps = settings.get("video_steps", nested.get("steps", VIDEO_DEFAULT_STEPS))
    steps_number = _as_number(raw_steps)
    steps = VIDEO_DEFAULT_STEPS if steps_number is None else int(max(1, min(50, round(steps_number))))

    raw_resolution = settings.get(
        "video_resolution", nested.get("resolution", VIDEO_DEFAULT_RESOLUTION)
    )
    resolution = str(raw_resolution).strip().lower() if raw_resolution is not None else ""
    if resolution in {"2k", "2048", "1440"}:
        resolution = "2k"
    elif resolution not in VIDEO_RESOLUTION_SHORT_EDGES:
        resolution = VIDEO_DEFAULT_RESOLUTION

    raw_duration = settings.get(
        "video_duration", nested.get("duration", VIDEO_DEFAULT_DURATION)
    )
    duration_number = _as_number(raw_duration)
    duration = VIDEO_DEFAULT_DURATION if duration_number is None else max(1.0, min(15.0, duration_number))
    duration = round(duration * 2) / 2

    return {
        "fast": settings.get("video_quick_mode") is True,
        "steps": steps,
        "resolution": resolution,
        "duration": duration,
    }


def resolve_video_dimensions(
    width: int | float | None,
    height: int | float | None,
    resolution: str,
    allowed_dimensions: Optional[Sequence[Sequence[int | float]]] = None,
) -> tuple[int, int]:
    """Resolve a resolution preset while preserving the requested aspect ratio.

    Providers with a constrained dimension list (including the H3 adapters) use
    the closest supported pair.  Unconstrained tools get a 32-pixel aligned
    pair, matching the H3 canvas convention.
    """

    target_short_edge = VIDEO_RESOLUTION_SHORT_EDGES.get(str(resolution).lower())
    if target_short_edge is None:
        target_short_edge = VIDEO_RESOLUTION_SHORT_EDGES[VIDEO_DEFAULT_RESOLUTION]

    source_width = _as_number(width) or 16 * 32
    source_height = _as_number(height) or 9 * 32
    aspect = max(0.1, source_width / max(source_height, 1.0))
    landscape = source_width >= source_height

    candidates: list[tuple[int, int]] = []
    for pair in allowed_dimensions or ():
        if len(pair) != 2:
            continue
        candidate_width = int(pair[0])
        candidate_height = int(pair[1])
        if candidate_width > 0 and candidate_height > 0:
            candidates.append((candidate_width, candidate_height))

    if candidates:
        oriented = [
            pair for pair in candidates
            if (pair[0] >= pair[1]) == landscape
        ] or candidates
        selected = min(
            oriented,
            key=lambda pair: (
                abs(min(pair) - target_short_edge),
                abs((pair[0] / pair[1]) - aspect),
            ),
        )
        return selected

    if landscape:
        short_edge = int(round(target_short_edge / 32) * 32)
        long_edge = int(round((short_edge * aspect) / 32) * 32)
        return max(short_edge, long_edge), min(short_edge, long_edge)

    short_edge = int(round(target_short_edge / 32) * 32)
    long_edge = int(round((short_edge / aspect) / 32) * 32)
    return min(short_edge, long_edge), max(short_edge, long_edge)


def apply_video_chat_preferences(
    job_params: dict[str, Any],
    width: int,
    height: int,
    parameter_properties: Mapping[str, Any],
    settings: Mapping[str, Any] | None,
    allowed_dimensions: Optional[Sequence[Sequence[int | float]]] = None,
) -> tuple[int, int, dict[str, Any]]:
    """Apply normalized chat preferences to a video job and return dimensions."""

    normalized = normalize_video_chat_settings(settings)
    if "steps" in parameter_properties:
        job_params["steps"] = VIDEO_FAST_STEPS if normalized["fast"] else normalized["steps"]
    if "duration" in parameter_properties:
        job_params["duration"] = normalized["duration"]

    if "width" in parameter_properties and "height" in parameter_properties:
        width, height = resolve_video_dimensions(
            width,
            height,
            normalized["resolution"],
            allowed_dimensions,
        )
        job_params["width"] = width
        job_params["height"] = height

    return width, height, normalized
