"""Automatic location prompt contracts derived from blocking and project lore.

The UI may accept an optional art-direction override, but canonical geography,
story state and negative constraints are generated here so a user never has to
retype the shot-map contract for every camera family.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Iterable


MNESIS_PROMPT_PROFILE = "mnesis-location-v1"
MNESIS_NIGHT = "APT_NIGHT_RAIN"
MNESIS_MORNING = "APT_MORNING"
MNESIS_EXTERIOR = "EXTERIOR_CORRIDOR_NIGHT"
MNESIS_CLINICAL = "MNESIS_CLINICAL"


def _normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


def is_mnesis_shot_map(shots: Iterable[Any]) -> bool:
    text = _normalized(" ".join(
        f"{getattr(shot, 'title', '')} {getattr(shot, 'description', '')}"
        for shot in shots
    ))
    return (
        "mnesis" in text
        and "maya" in text
    ) or all(marker in text for marker in ("maya", "judas", "troisieme maya"))


def advances_to_morning(shot: Any) -> bool:
    text = _normalized(f"{getattr(shot, 'title', '')} {getattr(shot, 'description', '')}")
    return any(term in text for term in (
        "lumiere blanche du matin",
        "matin",
        "la pluie a cesse",
        "rain has stopped",
        "morning light",
    ))


def location_state_for_shot(
    shot: Any,
    *,
    location_id: str,
    interior_phase: str,
    mnesis: bool,
) -> str:
    if not mnesis:
        return "default"
    text = _normalized(f"{getattr(shot, 'title', '')} {getattr(shot, 'description', '')}")
    if any(term in text for term in ("patient record", "clinique", "clinical", "administratif")):
        return MNESIS_CLINICAL
    if location_id == "exterior":
        return MNESIS_EXTERIOR
    return interior_phase


def _camera_family(spec: dict[str, Any]) -> str:
    camera = spec.get("camera") or {}
    location = spec.get("location") or {}
    return (
        f"Location zone: {location.get('label') or location.get('id') or 'unspecified'}. "
        f"Framing family: {camera.get('plan_type') or 'establishing view'}; "
        f"lens behavior: {camera.get('lens') or 'derived from approved blocking'}; "
        f"field of view: {camera.get('fov', 'derived')} degrees; "
        f"camera map position ({camera.get('x', 'derived')}, {camera.get('y', 'derived')}) "
        f"facing {camera.get('facing', 'derived')} degrees."
    )


def _state_contract(state: str) -> str:
    contracts = {
        MNESIS_NIGHT: (
            "APT_NIGHT_RAIN — the recurring Maya apartment at night: open kitchen, living area with low table, "
            "large rain-covered windows, entrance door and peephole relationship, dark internal hallway, and "
            "office opening deeper in the same fixed geography. Warm low interior light; cold rainy city separation."
        ),
        MNESIS_MORNING: (
            "APT_MORNING — exactly the same apartment identity, architecture, openings, fixed furniture and scale "
            "as APT_NIGHT_RAIN. Rain has stopped; clean white morning light enters; the apartment looks normal. "
            "Do not mirror or redesign the floor plan."
        ),
        MNESIS_EXTERIOR: (
            "EXTERIOR_CORRIDOR_NIGHT — the cold exterior corridor directly outside Maya's established entrance "
            "door. Door position, scale, swing side and peephole must remain spatially compatible with the approved apartment."
        ),
        MNESIS_CLINICAL: (
            "MNESIS_CLINICAL — a cold, restrained, credible administrative/clinical office, almost empty and "
            "completely distinct from Maya's apartment."
        ),
    }
    return contracts.get(state, "Preserve the exact approved location identity and visual state.")


def _geography_lock(location_id: str) -> str:
    locks = {
        "kitchen": (
            "The open kitchen must retain a credible line to the living area and large windows. The counter can "
            "frame the dark hallway deeper in the apartment without moving either zone."
        ),
        "living": (
            "The living area must retain the low-table zone, the open-kitchen relationship, large windows, and a "
            "credible route toward the entrance and internal hallway."
        ),
        "entry": (
            "Preserve the exact entrance door, peephole, threshold and the established relationship from the main "
            "room toward both the exterior corridor and internal hallway."
        ),
        "hallway": (
            "The internal hallway remains connected to the main room and leads toward one stable office opening at "
            "depth. Keep the corridor genuinely empty in the clean plate."
        ),
        "exterior": (
            "Face the same apartment door from the corridor side. Do not invent neighboring doors, windows or a "
            "second corridor to solve the framing."
        ),
    }
    return locks.get(location_id, "Preserve all established room relationships and fixed spatial anchors.")


def _shot_coverage_locks(shot_numbers: list[int]) -> list[str]:
    shot_set = set(shot_numbers)
    locks: list[str] = []
    if shot_set & {16, 29, 52}:
        locks.append("Support the established peephole POV and the exact corridor-to-door relationship.")
    if 46 in shot_set:
        locks.append("The hallway direction must lead visibly toward the office opening at apartment depth.")
    if 48 in shot_set:
        locks.append("The hallway is genuinely empty: no silhouette, person, reflection-person or shadow anomaly.")
    if shot_set & {51, 57}:
        locks.append("Keep the kitchen-counter foreground and dark hallway depth compatible in one unchanged geography.")
    if 56 in shot_set:
        locks.append("The frame must support a position between the entrance door and the internal hallway.")
    if 64 in shot_set:
        locks.append("Show clean bare counter and floor surfaces; no knife and no person anywhere in the location plate.")
    if 71 in shot_set:
        locks.append("Door geometry must be physically coherent for one continuous unlock, opening, entry and closing action.")
    if 85 in shot_set:
        locks.append(
            "The composition must support a slow pull-back that gradually reveals apartment depth and the single "
            "established dark office doorway. The clean plate contains no person."
        )
    return locks


def build_location_prompt_augmentation(spec: dict[str, Any]) -> str:
    """Return the automatic production lock appended to a location request."""
    location = spec.get("location") or {}
    camera = spec.get("camera") or {}
    shot_numbers = [
        int(number) for number in spec.get("shot_numbers") or []
        if isinstance(number, (int, float)) or str(number).isdigit()
    ]
    if spec.get("prompt_profile") != MNESIS_PROMPT_PROFILE:
        return (
            "AUTOMATIC BLOCKING AUGMENTATION\n"
            f"{_camera_family(spec)}\n"
            "Use the approved master as architectural identity. Keep one coherent clean plate with no people, "
            "captions, collage or unrequested movable story props.\n"
            f"Machine-readable blocking contract: {json.dumps({'camera': camera, 'location': location}, ensure_ascii=False)}"
        )

    state = str(spec.get("location_state") or MNESIS_NIGHT)
    location_id = str(location.get("id") or "")
    locks = _shot_coverage_locks(shot_numbers)
    lock_text = "\n".join(f"- {lock}" for lock in locks) if locks else "- Preserve the approved spatial anchors required by these shots."
    return (
        "MNESIS LOCATION SKILL — AUTOMATIC AUGMENTATION\n"
        f"ACTIVE LOCATION STATE\n{_state_contract(state)}\n\n"
        f"CAMERA FAMILY\n{_camera_family(spec)}\n\n"
        f"GEOGRAPHY LOCK\n{_geography_lock(location_id)}\n\n"
        f"SHOT COVERAGE ({', '.join(str(number) for number in shot_numbers) or 'master'})\n{lock_text}\n\n"
        "HARD NEGATIVES\n"
        "- No people, Maya, duplicate person, reflection-person or human-shaped background figure.\n"
        "- No extra hallway, doorway, window, room, toilet, random furniture or mirrored architecture.\n"
        "- No movable story prop, readable text, label, caption, collage or viewsheet layout.\n"
        "- A new camera angle is not permission to regenerate different architecture.\n\n"
        "OUTPUT\nOne production clean plate only, exact 16:9 canvas, ready for later character/prop composition."
    )
