"""World State domain service.

Aggregates ProjectDirection, ProjectElements (characters, locations, props),
Scenes and Continuity tracking buffers into a unified context layer for video
generation, interactive chat direction, and H3 Context-IR prompt distillation.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import (
    Asset,
    AssetRevision,
    Board,
    BoardAssetItem,
    MediaItem,
    Project,
    ProjectDirection,
    ProjectElement,
    ProjectScene,
)
from project_direction_service import direction_payload, json_value, scene_dict
from project_element_service import list_project_elements


async def build_project_world_state(
    session: AsyncSession,
    project_id: int,
    scene_id: Optional[int] = None,
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

    if scene_id is not None:
        for idx, s in enumerate(scenes):
            if s.id == scene_id:
                current_scene_data = scene_dict(s)
                if idx > 0:
                    previous_scene_data = scene_dict(scenes[idx - 1])
                if idx < len(scenes) - 1:
                    next_scene_data = scene_dict(scenes[idx + 1])
                break

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
