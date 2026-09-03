"""Validate H3 reference labels against the media attached to a generation.

MiniMax H3 does not treat ``<Picture N>``, ``<Video N>`` and ``<Audio N>`` as
ordinary prose: they are protocol labels used to bind prompt text to the
corresponding conditioning inputs.  A phantom label can therefore produce an
unusable result even when the provider reports a technically successful job.

This module deliberately contains no database or UI dependencies.  The REST
route, the agent SDK path, and the generation queue can all use the same check.
"""

from __future__ import annotations

import re
from typing import Any, Mapping


REFERENCE_TAG_RE = re.compile(
    r"<\s*(Picture|Video|Audio)\s+(\d+)\s*>",
    re.IGNORECASE,
)


def _count_values(value: Any) -> int:
    """Count concrete media values in the shapes accepted by STP parameters."""
    if value is None:
        return 0
    if isinstance(value, (list, tuple)):
        return sum(_count_values(item) for item in value)
    if isinstance(value, Mapping):
        # A set descriptor is expanded before an individual generation job is
        # created and is not itself a concrete reference for this check.
        return 0
    if isinstance(value, str):
        return 1 if value.strip() else 0
    return 1 if not isinstance(value, bool) else 0


def _kind_display(kind: str) -> str:
    return {"Picture": "image", "Video": "vidéo", "Audio": "audio"}.get(
        kind, kind.lower()
    )


def reference_prompt_mismatches(
    prompt: Any,
    parameters: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return mismatches for explicit H3 reference tags in ``prompt``.

    Only tags that are actually written in the prompt are checked.  An
    attached media input is allowed to be unused, so a prompt containing only
    ``<Picture N>`` tags never gets rejected merely because video/audio inputs
    are also present in the request.
    """
    if not isinstance(prompt, str) or not prompt.strip():
        return []

    params = parameters or {}
    image_count = _count_values(params.get("input_images"))
    video_count = _count_values(params.get("input_videos"))
    standalone_audio_count = _count_values(params.get("input_audios"))
    audio_count = video_count + standalone_audio_count

    tags = [
        (match.group(1).title(), int(match.group(2)), match.group(0))
        for match in REFERENCE_TAG_RE.finditer(prompt)
    ]
    available = {
        "Picture": image_count,
        "Video": video_count,
        "Audio": audio_count,
    }
    mismatches: list[dict[str, Any]] = []

    for kind, index, raw_tag in tags:
        count = available[kind]
        if index < 1 or index > count:
            if count == 0:
                reason = f"le prompt mentionne {raw_tag}, mais aucune référence {_kind_display(kind)} n'est attachée"
            else:
                reason = (
                    f"le prompt mentionne {raw_tag}, mais seulement {count} référence(s) "
                    f"{_kind_display(kind)} sont attachée(s)"
                )
            mismatches.append(
                {
                    "kind": kind.lower(),
                    "index": index,
                    "tag": raw_tag,
                    "type": "unknown_prompt_reference",
                    "reason": reason,
                }
            )

    return mismatches


def format_reference_prompt_warning(mismatches: list[dict[str, Any]]) -> str:
    """Build the user-facing confirmation text for a reference mismatch."""
    details = "\n".join(f"- {item.get('reason', 'Référence incohérente')}" for item in mismatches)
    return (
        "Attention : les références du prompt ne correspondent pas aux médias "
        "attachés à cette génération.\n\n"
        f"{details}\n\n"
        "Cela peut produire une vidéo incohérente ou corrompue. "
        "Êtes-vous sûr de vouloir démarrer la génération ?"
    )


class ReferencePromptMismatchError(ValueError):
    """Raised when a generation contains an unconfirmed H3 reference mismatch."""

    code = "generation_reference_mismatch"

    def __init__(self, mismatches: list[dict[str, Any]]):
        self.mismatches = mismatches
        super().__init__(format_reference_prompt_warning(mismatches))
