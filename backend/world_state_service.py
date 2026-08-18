"""World State domain service.

Aggregates ProjectDirection, ProjectElements (characters, locations, props),
Scenes and Continuity tracking buffers into a unified context layer for video
generation, interactive chat direction, and H3 Context-IR prompt distillation.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import (
    Asset,
    AssetRevision,
    Board,
    BoardAssetItem,
    BoardSection,
    MediaItem,
    Project,
    ProjectDirection,
    ProjectElement,
    ProjectScene,
)
from project_direction_service import direction_payload, json_value, scene_dict
from project_element_service import list_project_elements
from shot_continuity_service import (
    build_shot_generation_contract,
    latest_previous_shot_acceptance,
)


_AGENT_TEXT_LIMITS = {
    "description": 900,
    "scene_description": 500,
    "scene_prompt": 5000,
    "scene_context": 3500,
    "summary": 2500,
}

_SHOT_ROW_RE = re.compile(
    r"^\|\s*\*{0,2}(\d{1,3})\*{0,2}\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$",
    re.MULTILINE,
)


def infer_shot_number(shot_prompt: str | None) -> Optional[int]:
    """Read 'plan 04'/'shot 04' without confusing it with scene_number."""
    match = re.search(r"\b(?:plan|shot)\s*0*(\d+)\b", shot_prompt or "", re.IGNORECASE)
    return int(match.group(1)) if match else None


def extract_script_shots(script_text: str | None) -> list[dict[str, Any]]:
    """Parse the compact shot-map table stored inside a Direction scene."""
    shots = []
    for match in _SHOT_ROW_RE.finditer(script_text or ""):
        shot_number, duration, code, description, incoming_cut = match.groups()
        shots.append({
            "shot_number": int(shot_number),
            "duration": duration.strip(),
            "code": code.strip().replace("**", ""),
            "description": description.strip(),
            "incoming_cut": incoming_cut.strip(),
        })
    return shots


def build_script_shot_context(scene: dict[str, Any] | None, shot_number: int | None) -> dict[str, Any] | None:
    """Return the requested shot plus its neighboring script rows."""
    if not scene or shot_number is None:
        return None
    shots = extract_script_shots(scene.get("description") or scene.get("prompt"))
    if not shots:
        return {
            "shot_number": shot_number,
            "status": "not_found_in_scene_script",
            "scene_number": scene.get("scene_number"),
        }
    by_number = {shot["shot_number"]: shot for shot in shots}
    current = by_number.get(shot_number)
    if current is None:
        return {
            "shot_number": shot_number,
            "status": "not_found_in_scene_script",
            "scene_number": scene.get("scene_number"),
            "available_shot_numbers": sorted(by_number),
        }
    return {
        "status": "resolved",
        "scene_number": scene.get("scene_number"),
        "scene_title": scene.get("title"),
        "shot_number": shot_number,
        "current": current,
        "previous": by_number.get(shot_number - 1),
        "next": by_number.get(shot_number + 1),
        "continuity_policy": (
            "Use the previous shot's accepted last frame as a semantic continuity anchor. "
            "Preserve state and hand/prop relationships; do not copy framing unless the script requires frame-perfect matching."
        ),
    }


def build_shot_reference_manifest(
    world_state: Dict[str, Any],
    shot_context: dict[str, Any],
    previous_acceptance: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Select ordered, role-labelled references for one shot.

    The manifest deliberately prefers a close location element when the shot
    is kitchen-focused and never falls back to an arbitrary older generation.
    The agent may describe the prompt, but it cannot silently invent the
    Picture ordering after this point.
    """
    current = shot_context.get("current") or {}
    text = " ".join(str(current.get(key) or "") for key in ("description", "incoming_cut")).casefold()
    entities = world_state.get("entities") or {}
    manifest: list[dict[str, Any]] = []
    seen: set[int] = set()

    def add(item: dict[str, Any] | None, role: str, reason: str) -> None:
        if not item or not item.get("media_id"):
            return
        media_id = int(item["media_id"])
        if media_id in seen:
            return
        seen.add(media_id)
        manifest.append({
            "label": f"Picture {len(manifest) + 1}",
            "media_id": media_id,
            "role": role,
            "reference_id": item.get("reference_id"),
            "name": item.get("name"),
            "reason": reason,
        })

    previous_frame_id = (previous_acceptance or {}).get("last_frame_media_id")
    if previous_frame_id:
        add({"media_id": previous_frame_id, "reference_id": "continuity_previous_last_frame", "name": "previous accepted last frame"}, "continuity_anchor", "accepted last frame of the immediately preceding shot")

    characters = list((entities.get("characters") or {}).values())
    if characters and any(token in text for token in ("maya", "character", "woman", "personnage")):
        add(characters[0], "character", "canonical character identity")

    locations = list((entities.get("locations") or {}).values())
    def _location_priority(item: dict[str, Any]) -> tuple[int, int]:
        identity = " ".join(str(item.get(key) or "") for key in ("name", "reference_id")).casefold()
        description = str(item.get("description") or "").casefold()
        return (
            0 if any(token in identity for token in ("kitchen", "cuisine")) else 1,
            0 if any(token in description for token in ("kitchen", "cuisine")) else 1,
        )

    kitchen_locations = sorted(
        [
            item for item in locations
            if any(token in " ".join(str(item.get(key) or "") for key in ("name", "reference_id", "description")).casefold() for token in ("kitchen", "cuisine"))
        ],
        key=_location_priority,
    )
    if any(token in text for token in ("kitchen", "cuisine", "cuisine ouverte")) and kitchen_locations:
        add(kitchen_locations[0], "location_canonical", "kitchen-focused location reference")
    elif locations:
        add(locations[0], "location_canonical", "scene location reference")

    props = list((entities.get("props") or {}).values())
    prop_tokens = (
        ("sachet", "tea bag", "tea-bag", "thé"),
        ("tasse", "mug", "cup"),
        ("bouilloire", "kettle"),
        ("fenêtre", "fenetre", "window"),
    )
    for tokens in prop_tokens:
        if not any(token in text for token in tokens):
            continue
        identity_match = next(
            (
                item for item in props
                if any(token in " ".join(str(item.get(key) or "") for key in ("name", "reference_id")).casefold() for token in tokens)
            ),
            None,
        )
        match = identity_match or next(
            (
                item for item in props
                if any(token in str(item.get("description") or "").casefold() for token in tokens)
            ),
            None,
        )
        add(match, "prop", f"prop required by shot: {tokens[0]}")

    return manifest


def _agent_text(value: Any, limit: int) -> str:
    text = str(value or "")
    return text if len(text) <= limit else f"{text[:limit]}… [truncated]"


def _compact_agent_json(value: Any, *, limit: int, depth: int = 0) -> Any:
    """Keep structured continuity context useful without flooding the LLM."""
    if depth > 4:
        return "[depth limit]"
    if isinstance(value, dict):
        items = list(value.items())[:40]
        return {
            str(key): _compact_agent_json(item, limit=limit, depth=depth + 1)
            for key, item in items
        }
    if isinstance(value, list):
        return [
            _compact_agent_json(item, limit=limit, depth=depth + 1)
            for item in value[:40]
        ]
    if isinstance(value, str):
        return _agent_text(value, limit)
    return value


def _compact_agent_element(element: dict[str, Any]) -> dict[str, Any]:
    """Expose stable ids and descriptions, omitting bookkeeping/timestamps."""
    return {
        key: element.get(key)
        for key in (
            "id", "project_id", "asset_id", "revision_id", "media_id",
            "element_type", "name", "reference_id", "file_format",
        )
    } | {
        "description": _agent_text(
            element.get("description"), _AGENT_TEXT_LIMITS["description"]
        ),
    }


def _compact_agent_scene(scene: dict[str, Any], *, include_context: bool = False) -> dict[str, Any]:
    compact = {
        key: scene.get(key)
        for key in (
            "id", "project_id", "board_id", "sequence_number", "scene_number",
            "title", "status", "validation_status", "generation_count",
        )
    }
    compact["description"] = _agent_text(
        scene.get("description"), _AGENT_TEXT_LIMITS["scene_description"]
    )
    if include_context:
        compact["prompt"] = _agent_text(
            scene.get("prompt"), _AGENT_TEXT_LIMITS["scene_prompt"]
        )
        compact["context"] = _compact_agent_json(
            scene.get("context") or {}, limit=_AGENT_TEXT_LIMITS["scene_context"]
        )
        compact["dependencies"] = (scene.get("dependencies") or [])[:20]
        compact["blockers"] = (scene.get("blockers") or [])[:20]
    return compact


def compact_world_state_for_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """Return an LLM-sized World State while retaining continuity identities."""
    entities = state.get("entities") or {}
    compact_entities = {
        group: {
            ref_id: _compact_agent_element(element)
            for ref_id, element in (entities.get(group) or {}).items()
        }
        for group in ("characters", "locations", "props")
    }
    compact = {
        "project_id": state.get("project_id"),
        "project_name": state.get("project_name"),
        "script_name": state.get("script_name"),
        "summary": _agent_text(state.get("summary"), _AGENT_TEXT_LIMITS["summary"]),
        "global_context": _compact_agent_json(
            state.get("global_context") or {}, limit=3500
        ),
        "entities": compact_entities,
        "total_scenes": state.get("total_scenes", 0),
        "scenes": [
            _compact_agent_scene(scene)
            for scene in (state.get("scenes") or [])[:100]
        ],
        "current_scene": (
            _compact_agent_scene(state["current_scene"], include_context=True)
            if state.get("current_scene") else None
        ),
        "previous_scene": (
            _compact_agent_scene(state["previous_scene"], include_context=True)
            if state.get("previous_scene") else None
        ),
        "next_scene": (
            _compact_agent_scene(state["next_scene"], include_context=True)
            if state.get("next_scene") else None
        ),
        "continuity_buffer": _compact_agent_json(
            state.get("continuity_buffer") or {}, limit=3500
        ),
        "reference_assets": state.get("reference_assets") or [],
        "world_state_compacted": True,
    }
    shot_context = state.get("shot_context")
    if isinstance(shot_context, dict):
        compact["shot_context"] = _compact_agent_json(shot_context, limit=5000)
    if isinstance(state.get("generation_contract"), dict):
        compact["generation_contract"] = _compact_agent_json(
            state["generation_contract"], limit=5000
        )
    if "missing_references" in state:
        compact["missing_references"] = state.get("missing_references") or []
        compact["has_missing_references"] = bool(state.get("has_missing_references"))
    return compact


async def resolve_project_scene(
    session: AsyncSession,
    *,
    project_id: int,
    scene_id: Optional[int] = None,
    sequence_number: Optional[int] = None,
    scene_number: Optional[int] = None,
    board_id: Optional[int] = None,
) -> Optional[ProjectScene]:
    """Resolve a scene using stable project coordinates, never chat-local state.

    Scene chats carry a scene id in their instructions, but ordinary project or
    board chats do not.  This lookup is intentionally scoped to the chat's
    project so a board/scene id from another project cannot leak context.
    """
    stmt = select(ProjectScene).where(ProjectScene.project_id == project_id)
    if scene_id is not None:
        stmt = stmt.where(ProjectScene.id == scene_id)
    elif board_id is not None:
        stmt = stmt.where(ProjectScene.board_id == board_id)
    else:
        if sequence_number is not None:
            stmt = stmt.where(ProjectScene.sequence_number == sequence_number)
        if scene_number is not None:
            stmt = stmt.where(ProjectScene.scene_number == scene_number)

    return await session.scalar(
        stmt.order_by(ProjectScene.sequence_number, ProjectScene.scene_number, ProjectScene.id)
    )


async def _board_reference_assets(session: AsyncSession, board_id: Optional[int]) -> list[dict[str, Any]]:
    """Return the live visual assets in a scene board's References section."""
    if board_id is None:
        return []

    rows = (
        await session.execute(
            select(BoardSection.name, Asset, AssetRevision, MediaItem)
            .join(BoardAssetItem, BoardAssetItem.board_section_id == BoardSection.id)
            .join(Asset, Asset.id == BoardAssetItem.asset_id)
            .outerjoin(
                AssetRevision,
                (AssetRevision.id == Asset.current_revision_id)
                & AssetRevision.deleted_at.is_(None),
            )
            .outerjoin(
                MediaItem,
                (MediaItem.id == AssetRevision.primary_media_id)
                & MediaItem.deleted_at.is_(None)
                & (
                    MediaItem.file_unavailable.is_(False)
                    | MediaItem.file_unavailable.is_(None)
                ),
            )
            .where(
                BoardSection.board_id == board_id,
                BoardSection.deleted_at.is_(None),
                func.lower(func.trim(BoardSection.name)) == "references",
                BoardAssetItem.deleted_at.is_(None),
                Asset.state == "active",
                Asset.deleted_at.is_(None),
            )
            .order_by(BoardAssetItem.display_order, BoardAssetItem.id)
        )
    ).all()

    return [
        {
            "asset_id": asset.id,
            "title": asset.title,
            "section": section_name,
            "revision_id": revision.id if revision else None,
            "media_id": media.id if media else None,
            "file_hash": media.file_hash if media else None,
            "file_format": media.file_format if media else None,
        }
        for section_name, asset, revision, media in rows
    ]


async def build_project_world_state(
    session: AsyncSession,
    project_id: int,
    scene_id: Optional[int] = None,
    sequence_number: Optional[int] = None,
    scene_number: Optional[int] = None,
    board_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Aggregate project direction, elements, and continuity buffer into a unified World State."""
    project = await session.get(Project, project_id)
    if not project or project.deleted_at is not None:
        return {"error": f"Project {project_id} not found"}

    direction = await session.get(ProjectDirection, project_id)
    global_context = json_value(direction.context if direction else None, {})

    raw_elements = await list_project_elements(session, project_id=project_id)
    characters: Dict[str, Any] = {}
    locations: Dict[str, Any] = {}
    props: Dict[str, Any] = {}

    for elem in raw_elements:
        etype = elem.get("element_type")
        ref_id = elem.get("reference_id") or f"elem_{elem.get('id')}"
        if etype == "character":
            characters[ref_id] = elem
        elif etype == "location":
            locations[ref_id] = elem
        else:
            props[ref_id] = elem

    # Fetch all project scenes ordered
    stmt = (
        select(ProjectScene)
        .where(ProjectScene.project_id == project_id)
        .order_by(ProjectScene.sequence_number, ProjectScene.scene_number)
    )
    scenes = (await session.scalars(stmt)).all()
    scene_list = [scene_dict(s) for s in scenes]

    current_scene_data: Optional[Dict[str, Any]] = None
    previous_scene_data: Optional[Dict[str, Any]] = None
    next_scene_data: Optional[Dict[str, Any]] = None

    resolved_scene = await resolve_project_scene(
        session,
        project_id=project_id,
        scene_id=scene_id,
        sequence_number=sequence_number,
        scene_number=scene_number,
        board_id=board_id,
    )
    resolved_scene_id = resolved_scene.id if resolved_scene else None

    if resolved_scene_id is not None:
        for idx, s in enumerate(scenes):
            if s.id == resolved_scene_id:
                current_scene_data = scene_dict(s)
                if idx > 0:
                    previous_scene_data = scene_dict(scenes[idx - 1])
                if idx < len(scenes) - 1:
                    next_scene_data = scene_dict(scenes[idx + 1])
                break

    reference_assets = await _board_reference_assets(
        session,
        current_scene_data.get("board_id") if current_scene_data else board_id,
    )

    # Extract continuity buffer from previous scene context if available
    continuity_buffer: Dict[str, Any] = {}
    if previous_scene_data:
        prev_ctx = previous_scene_data.get("context", {})
        if isinstance(prev_ctx, dict):
            continuity_buffer = prev_ctx.get("continuity", {})

    return {
        "project_id": project_id,
        "project_name": project.name,
        "script_name": direction.script_name if direction else None,
        "summary": direction.summary if direction else "",
        "global_context": global_context,
        "entities": {
            "characters": characters,
            "locations": locations,
            "props": props,
        },
        "total_scenes": len(scene_list),
        "scenes": scene_list,
        "current_scene": current_scene_data,
        "previous_scene": previous_scene_data,
        "next_scene": next_scene_data,
        "continuity_buffer": continuity_buffer,
        "reference_assets": reference_assets,
    }


def detect_missing_references(
    world_state: Dict[str, Any],
    shot_prompt: str,
) -> List[Dict[str, Any]]:
    """Scan the prompt and current scene for entity mentions lacking visual asset references."""
    missing: List[Dict[str, Any]] = []
    text_to_scan = (shot_prompt or "").lower()

    current_scene = world_state.get("current_scene")
    if current_scene:
        desc = (current_scene.get("description") or "").lower()
        title = (current_scene.get("title") or "").lower()
        text_to_scan = f"{text_to_scan} {desc} {title}"

    entities = world_state.get("entities", {})
    all_entity_groups = [
        ("character", entities.get("characters", {})),
        ("location", entities.get("locations", {})),
        ("prop", entities.get("props", {})),
    ]

    for etype, group in all_entity_groups:
        for ref_id, elem in group.items():
            name = (elem.get("name") or "").strip().lower()
            ref_token = f"@{ref_id.lower()}"

            # Check if full name, significant name words, or explicit @reference is present in the prompt/scene
            name_words = [w for w in re.findall(r"\w+", name) if len(w) >= 3 and w not in {"the", "and", "for", "with", "dans", "avec", "pour", "les", "des", "une"}]
            is_referenced = (
                (name and name in text_to_scan)
                or (ref_token in text_to_scan)
                or (ref_id.lower() in text_to_scan)
                or any(w in text_to_scan for w in name_words)
            )

            if is_referenced:
                has_asset = bool(elem.get("asset_id") and elem.get("media_id"))
                if not has_asset:
                    missing.append({
                        "id": elem.get("id"),
                        "reference_id": ref_id,
                        "name": elem.get("name"),
                        "element_type": etype,
                        "description": elem.get("description") or "",
                        "reason": f"Visual reference missing for {etype} '{elem.get('name')}'",
                    })

    return missing


async def update_entity_state(
    session: AsyncSession,
    project_id: int,
    reference_id: str,
    *,
    description: Optional[str] = None,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """Update a project element's description or active state."""
    stmt = select(ProjectElement).where(
        ProjectElement.project_id == project_id,
        ProjectElement.reference_id == reference_id,
        ProjectElement.deleted_at.is_(None),
    )
    element = await session.scalar(stmt)
    if not element:
        return {"error": f"Element @{reference_id} not found in project {project_id}"}

    if description is not None:
        element.description = description.strip() or None
    if name is not None:
        element.name = name.strip()

    await session.flush()
    return {
        "id": element.id,
        "reference_id": element.reference_id,
        "name": element.name,
        "element_type": element.element_type,
        "description": element.description,
        "updated": True,
    }


def distill_h3_shot_context(
    world_state: Dict[str, Any],
    shot_prompt: str,
    *,
    duration: float = 5.0,
    task: str = "ref2va",
) -> Tuple[str, List[Dict[str, Any]]]:
    """Compile World State & shot intent into a dense H3 Context-IR prompt (2-4k chars) + reference manifest."""
    entities = world_state.get("entities", {})
    text_lower = (shot_prompt or "").lower()

    active_references: List[Dict[str, Any]] = []
    character_context_lines: List[str] = []
    location_context_lines: List[str] = []

    # Identify active character references
    for ref_id, elem in entities.get("characters", {}).items():
        name = (elem.get("name") or "").lower()
        if name in text_lower or ref_id.lower() in text_lower:
            desc = elem.get("description") or ""
            character_context_lines.append(f"{elem.get('name')}: {desc}" if desc else elem.get('name'))
            if elem.get("media_id"):
                label = f"Picture {len(active_references) + 1}"
                active_references.append({
                    "label": label,
                    "media_id": elem.get("media_id"),
                    "asset_id": elem.get("asset_id"),
                    "name": elem.get("name"),
                    "element_type": "character",
                    "reference_id": ref_id,
                })

    # Identify active location references
    for ref_id, elem in entities.get("locations", {}).items():
        name = (elem.get("name") or "").lower()
        if name in text_lower or ref_id.lower() in text_lower or f"@{ref_id.lower()}" in text_lower:
            desc = elem.get("description") or ""
            location_context_lines.append(f"{elem.get('name')}: {desc}" if desc else elem.get('name'))
            if elem.get("media_id"):
                label = f"Picture {len(active_references) + 1}"
                active_references.append({
                    "label": label,
                    "media_id": elem.get("media_id"),
                    "asset_id": elem.get("asset_id"),
                    "name": elem.get("name"),
                    "element_type": "location",
                    "reference_id": ref_id,
                })

    # Identify active prop references
    for ref_id, elem in entities.get("props", {}).items():
        name = (elem.get("name") or "").lower()
        if name in text_lower or ref_id.lower() in text_lower or f"@{ref_id.lower()}" in text_lower:
            desc = elem.get("description") or ""
            if elem.get("media_id"):
                label = f"Picture {len(active_references) + 1}"
                active_references.append({
                    "label": label,
                    "media_id": elem.get("media_id"),
                    "asset_id": elem.get("asset_id"),
                    "name": elem.get("name"),
                    "element_type": "prop",
                    "reference_id": ref_id,
                })

    # Continuity buffer from previous frame
    continuity = world_state.get("continuity_buffer", {})
    continuity_note = ""
    if continuity:
        pose = continuity.get("maya_pose") or continuity.get("character_pose")
        cam = continuity.get("camera")
        if pose or cam:
            continuity_note = f" Starting continuity: {cam or ''} {pose or ''}".strip()

    # Compose H3 Context-IR fields
    visual_body = shot_prompt.strip()
    if continuity_note:
        visual_body = f"{visual_body}. {continuity_note}"

    ref_tags = " ".join([f"<{item['label']}>" for item in active_references])
    if ref_tags:
        visual_body = f"{ref_tags} {visual_body}"

    # Structure into MiniMax H3 Base schema
    ir_prompt = (
        f"integrated_multimodal_description: [Shot 1] {visual_body}\n\n"
        f"overall_soundscape: Diegetic environmental sounds, natural ambient atmosphere.\n\n"
        f"non_diegetic_music: N/A"
    )

    return ir_prompt, active_references
