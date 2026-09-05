"""Runtime posture switches for the desktop backend.

The desktop build in this checkout uses the local H3 gateway and Codex/agy
for generation.  ``main.py`` enables lean mode for that build; keeping the
switch environment-based lets tests and alternate distributions opt out
without changing persisted user configuration.
"""

from __future__ import annotations

import os
from typing import Any


LEAN_MODE_ENV = "STIMMA_LEAN_MODE"
_TRUTHY = {"1", "true", "yes", "on"}


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in _TRUTHY


def is_lean_mode() -> bool:
    """Return whether the local desktop process uses the lean posture."""

    return _truthy(os.environ.get(LEAN_MODE_ENV))


def is_stimma_cloud_enabled() -> bool:
    """Stimma Cloud account/tools are not part of the lean desktop path."""

    return not is_lean_mode()


def local_vision_enabled() -> bool:
    """Whether optional local CLIP/face/SAM3/ControlNet work is allowed."""

    return not is_lean_mode()


def lean_disabled_message(feature: str) -> str:
    """Return a user-facing explanation for a feature omitted by lean mode."""

    return f"{feature} unavailable in lean mode."


def ingestion_required(settings: Any) -> bool:
    """Return whether a background ingestion process has useful work.

    Uploads already extract their metadata inline in ``upload_service``.  A
    separate process is therefore unnecessary when there are no watched source
    folders and all optional background AI phases are disabled.
    """

    profiles = getattr(settings, "profiles", []) or []
    has_watched_folders = any(
        bool(getattr(profile, "folders", None)) for profile in profiles
    )
    if has_watched_folders:
        return True

    return any(
        bool(getattr(settings, section, None) and getattr(getattr(settings, section), "enabled", False))
        for section in ("clip", "face_detection", "captioning")
    )
