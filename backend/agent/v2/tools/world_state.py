"""Agent primitives for the Project World State and memory layer."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ..tools_registry import ToolParameter, tool
from world_state_service import (
    build_project_world_state,
    detect_missing_references,
    update_entity_state,
)


@tool(
    name="get_world_state",
    description=(
        "Read the unified project World State: characters, locations, props, active wardrobe/props, "
        "scene sequence, continuity buffer from the previous shot, and missing reference alerts for a prompt. "
        "Always call this before generating or planning video scenes to ensure character and location visual continuity."
    ),
    parameters=[
        ToolParameter(
            name="scene_id",
            type="integer",
            description="Optional current scene ID to fetch focused scene context and continuity from previous scene",
            required=False,
        ),
        ToolParameter(
            name="shot_prompt",
            type="string",
            description="Optional shot description to check for missing visual references (@char_..., @loc_...)",
            required=False,
        ),
    ],
    scope="agent",
)
async def get_world_state(
    scene_id: Optional[int] = None,
    shot_prompt: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    session: AsyncSession = kwargs.get("session")
    project_id: Optional[int] = kwargs.get("project_id")
    if not session or not project_id:
        return {"error": "This chat is not attached to a project."}

    state = await build_project_world_state(session, project_id=project_id, scene_id=scene_id)
    if "error" in state:
        return state

    missing = []
    if shot_prompt or state.get("current_scene"):
        missing = detect_missing_references(state, shot_prompt or "")

    state["missing_references"] = missing
    state["has_missing_references"] = len(missing) > 0
    return state


@tool(
    name="update_world_state",
    description=(
        "Update the active state or description of a character, location, or prop in the World State "
        "(e.g. changing wardrobe, carrying an accessory, updating a scene setting). "
        "Survives across chats and keeps visual continuity intact."
    ),
    parameters=[
        ToolParameter(
            name="reference_id",
            type="string",
            description="The entity reference ID (e.g. 'char_maya_maya', 'loc_apt_kitchen')",
            required=True,
        ),
        ToolParameter(
            name="description",
            type="string",
            description="Updated description or active state notes (e.g. 'Wearing oversized wool sweater, holding mug')",
            required=False,
        ),
        ToolParameter(
            name="name",
            type="string",
            description="Updated display name",
            required=False,
        ),
    ],
    scope="agent",
)
async def update_world_state(
    reference_id: str,
    description: Optional[str] = None,
    name: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    session: AsyncSession = kwargs.get("session")
    project_id: Optional[int] = kwargs.get("project_id")
    if not session or not project_id:
        return {"error": "This chat is not attached to a project."}

    ref = reference_id.lstrip("@").strip()
    result = await update_entity_state(
        session,
        project_id=project_id,
        reference_id=ref,
        description=description,
        name=name,
    )
    if "error" in result:
        return result

    await session.commit()
    return result
