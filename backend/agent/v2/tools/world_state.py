"""Agent primitives for the Project World State and memory layer."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ..tools_registry import ToolParameter, tool
from world_state_service import (
    build_project_world_state,
    build_shot_reference_manifest,
    build_script_shot_context,
    compact_world_state_for_agent,
    detect_missing_references,
    infer_shot_number,
    update_entity_state,
)
from shot_continuity_service import (
    build_shot_generation_contract,
    ensure_last_frame_media,
    list_shot_generation_candidates,
    latest_shot_acceptance,
    latest_previous_shot_acceptance,
    record_shot_acceptance,
    resolve_contract_last_frame,
)


@tool(
    name="get_world_state",
    description=(
        "Read the unified project World State: characters, locations, props, active wardrobe/props, "
        "scene sequence, continuity buffer from the previous shot, and missing reference alerts for a prompt. "
        "Use only in a chat attached to a project, when project-scoped scene or continuity data is needed; "
        "standalone chats should dispatch from their current prompt and attached references directly."
    ),
    parameters=[
        ToolParameter(
            name="scene_id",
            type="integer",
            description="Optional scene id for a focused lookup; use this when the scene id is already known",
            required=False,
        ),
        ToolParameter(
            name="sequence_number",
            type="integer",
            description="Optional sequence number from the user's request, for example 1 in 'sequence 1, scene 3'",
            required=False,
        ),
        ToolParameter(
            name="scene_number",
            type="integer",
            description="Optional scene number from the user's request, for example 3 in 'sequence 1, scene 3'",
            required=False,
        ),
        ToolParameter(
            name="shot_number",
            type="integer",
            description="Optional plan/shot number inside the resolved scene; this is distinct from scene_number",
            required=False,
        ),
        ToolParameter(
            name="board_id",
            type="integer",
            description="Optional scene board id when the user identifies the board instead of the scene",
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
    sequence_number: Optional[int] = None,
    scene_number: Optional[int] = None,
    shot_number: Optional[int] = None,
    board_id: Optional[int] = None,
    shot_prompt: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    session: AsyncSession = kwargs.get("session")
    project_id: Optional[int] = kwargs.get("project_id")
    if not session or not project_id:
        return {"error": "This chat is not attached to a project."}

    requested_shot_number = shot_number or infer_shot_number(shot_prompt)
    state = await build_project_world_state(
        session,
        project_id=project_id,
        scene_id=scene_id,
        sequence_number=sequence_number,
        scene_number=scene_number,
        board_id=board_id,
        shot_number=requested_shot_number,
    )
    if "error" in state:
        return state

    if (
        (scene_id is not None or board_id is not None
         or sequence_number is not None or scene_number is not None)
        and state.get("current_scene") is None
    ):
        selector = []
        if sequence_number is not None:
            selector.append(f"sequence {sequence_number}")
        if scene_number is not None:
            selector.append(f"scene {scene_number}")
        if board_id is not None:
            selector.append(f"board {board_id}")
        if scene_id is not None:
            selector.append(f"scene id {scene_id}")
        return {
            "error": f"No scene found for {', '.join(selector)} in project {project_id}.",
            "available_scenes": [
                {
                    "id": scene.get("id"),
                    "sequence_number": scene.get("sequence_number"),
                    "scene_number": scene.get("scene_number"),
                    "title": scene.get("title"),
                    "board_id": scene.get("board_id"),
                }
                for scene in state.get("scenes", [])
            ],
        }

    if requested_shot_number is not None:
        shot_context = build_script_shot_context(
            state.get("current_scene"),
            requested_shot_number,
            previous_shot=(state.get("shot_navigation") or {}).get("previous"),
            next_shot=(state.get("shot_navigation") or {}).get("next"),
        )
        if shot_context:
            state["shot_context"] = shot_context
        if not shot_context or shot_context.get("status") != "resolved":
            state["missing_references"] = []
            state["has_missing_references"] = False
            return compact_world_state_for_agent(state)
        if shot_context:
            previous_acceptance = None
            current_scene = state.get("current_scene") or {}
            if current_scene.get("id"):
                previous_acceptance = await latest_previous_shot_acceptance(
                    session,
                    project_id=int(project_id),
                    scene_id=int(current_scene["id"]),
                    shot_number=int(requested_shot_number),
                )
            reference_manifest = build_shot_reference_manifest(
                state, shot_context, previous_acceptance
            )
            shot_context["reference_manifest"] = reference_manifest
            shot_context["previous_accepted"] = previous_acceptance
            contract = build_shot_generation_contract(
                project_id=int(project_id),
                scene=current_scene,
                shot_context=shot_context,
                reference_manifest=reference_manifest,
                previous_acceptance=previous_acceptance,
            )
            if contract.get("previous_last_frame_media_id"):
                try:
                    await resolve_contract_last_frame(
                        session,
                        contract=contract,
                        workspace_dir=kwargs.get("workspace_dir"),
                    )
                    shot_context["reference_manifest"] = contract.get("reference_manifest") or reference_manifest
                except (RuntimeError, ValueError) as exc:
                    contract["continuity_materialization_error"] = str(exc)
            state["generation_contract"] = contract
    missing = []
    if shot_prompt or state.get("current_scene"):
        missing = detect_missing_references(state, shot_prompt or "")

    state["missing_references"] = missing
    state["has_missing_references"] = len(missing) > 0
    return compact_world_state_for_agent(state)


@tool(
    name="list_shot_generations",
    description=(
        "Find recent completed generation candidates for one exact plan/shot. "
        "Use this when the user asks for the latest frame, when the accepted output is unknown, "
        "or when several recent videos could match. Candidates include media IDs for preview, "
        "favorite/like state, and the currently accepted candidate when one exists."
    ),
    parameters=[
        ToolParameter(name="shot_number", type="integer", description="Plan/shot number inside the resolved scene", required=True),
        ToolParameter(name="scene_id", type="integer", description="Optional exact scene id", required=False),
        ToolParameter(name="sequence_number", type="integer", description="Optional Direction sequence number", required=False),
        ToolParameter(name="scene_number", type="integer", description="Optional Direction scene number", required=False),
        ToolParameter(name="board_id", type="integer", description="Optional scene board id", required=False),
        ToolParameter(name="limit", type="integer", description="Maximum recent candidates (default 8)", required=False),
    ],
    scope="agent",
)
async def list_shot_generations(
    shot_number: int,
    scene_id: Optional[int] = None,
    sequence_number: Optional[int] = None,
    scene_number: Optional[int] = None,
    board_id: Optional[int] = None,
    limit: int = 8,
    **kwargs: Any,
) -> Dict[str, Any]:
    session: AsyncSession = kwargs.get("session")
    project_id: Optional[int] = kwargs.get("project_id")
    if not session or not project_id:
        return {"error": "This chat is not attached to a project."}
    state = await build_project_world_state(
        session,
        project_id=project_id,
        scene_id=scene_id,
        sequence_number=sequence_number,
        scene_number=scene_number,
        board_id=board_id,
        shot_number=shot_number,
    )
    if state.get("error"):
        return state
    scene = state.get("current_scene") or {}
    if not scene.get("id"):
        return {"error": "No scene found for the requested plan."}
    candidates = await list_shot_generation_candidates(
        session,
        project_id=int(project_id),
        scene_id=int(scene["id"]),
        shot_number=int(shot_number),
        limit=limit,
    )
    accepted = None
    for candidate in candidates:
        if candidate.get("is_accepted"):
            accepted = candidate
        preview_media_id = candidate.get("last_frame_media_id") or candidate["media_id"]
        candidate["preview"] = f"![génération {candidate['index']}](media:{preview_media_id})"
    if accepted is None:
        accepted_record = await latest_shot_acceptance(
            session,
            project_id=int(project_id),
            scene_id=int(scene["id"]),
            shot_number=int(shot_number),
        )
        if accepted_record:
            accepted = {
                "media_id": accepted_record.get("media_id"),
                "last_frame_media_id": accepted_record.get("last_frame_media_id"),
                "job_id": accepted_record.get("generation_job_id"),
                "is_accepted": True,
                "preview": (
                    f"![dernière frame du plan {shot_number}]"
                    f"(media:{accepted_record.get('last_frame_media_id') or accepted_record.get('media_id')})"
                ),
            }
    return {
        "scene": {
            "id": scene.get("id"),
            "sequence_number": scene.get("sequence_number"),
            "scene_number": scene.get("scene_number"),
            "title": scene.get("title"),
        },
        "shot_number": int(shot_number),
        "accepted_candidate": accepted,
        "candidates": candidates,
        "count": len(candidates),
        "selection_instruction": "Preview the candidates in chat. Exact-shot candidates are authoritative; scene_recent candidates are review suggestions when older jobs lack shot metadata. Select by index, media_id, or the candidate marked is_favorite=true.",
    }


@tool(
    name="accept_shot_generation",
    description=(
        "Accept one selected video/image generation for a plan/shot and materialize its final frame "
        "as the continuity anchor. Use after the user chooses a candidate by index, media ID, or like/favorite."
    ),
    parameters=[
        ToolParameter(name="shot_number", type="integer", description="Plan/shot number inside the resolved scene", required=True),
        ToolParameter(name="media_id", type="integer", description="Selected generated video/image media ID", required=True),
        ToolParameter(name="scene_id", type="integer", description="Optional exact scene id", required=False),
        ToolParameter(name="sequence_number", type="integer", description="Optional Direction sequence number", required=False),
        ToolParameter(name="scene_number", type="integer", description="Optional Direction scene number", required=False),
        ToolParameter(name="board_id", type="integer", description="Optional scene board id", required=False),
    ],
    scope="agent",
)
async def accept_shot_generation(
    shot_number: int,
    media_id: int,
    scene_id: Optional[int] = None,
    sequence_number: Optional[int] = None,
    scene_number: Optional[int] = None,
    board_id: Optional[int] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    session: AsyncSession = kwargs.get("session")
    project_id: Optional[int] = kwargs.get("project_id")
    if not session or not project_id:
        return {"error": "This chat is not attached to a project."}
    state = await build_project_world_state(
        session,
        project_id=project_id,
        scene_id=scene_id,
        sequence_number=sequence_number,
        scene_number=scene_number,
        board_id=board_id,
        shot_number=shot_number,
    )
    if state.get("error"):
        return state
    scene = state.get("current_scene") or {}
    if not scene.get("id"):
        return {"error": "No scene found for the requested plan."}
    candidates = await list_shot_generation_candidates(
        session,
        project_id=int(project_id),
        scene_id=int(scene["id"]),
        shot_number=int(shot_number),
        limit=20,
    )
    candidate = next((item for item in candidates if int(item["media_id"]) == int(media_id)), None)
    if candidate is None:
        return {"error": f"Media {media_id} is not a completed generation candidate for shot {shot_number}."}
    if candidate.get("match_confidence") != "exact_shot" or not candidate.get("approval_eligible"):
        return {
            "error": (
                f"Media {media_id} is only a scene-level suggestion, not an exact candidate for shot {shot_number}. "
                "Regenerate with the canonical shot contract before accepting it."
            )
        }

    shot_context = build_script_shot_context(scene, int(shot_number))
    if not shot_context:
        return {"error": f"Shot {shot_number} is not present in the selected scene."}
    previous_acceptance = await latest_previous_shot_acceptance(
        session,
        project_id=int(project_id),
        scene_id=int(scene["id"]),
        shot_number=int(shot_number),
    )
    reference_manifest = build_shot_reference_manifest(state, shot_context, previous_acceptance)
    contract = build_shot_generation_contract(
        project_id=int(project_id),
        scene=scene,
        shot_context=shot_context,
        reference_manifest=reference_manifest,
        previous_acceptance=previous_acceptance,
    )
    try:
        last_frame_media_id = await ensure_last_frame_media(
            session,
            source_media_id=int(media_id),
            workspace_dir=kwargs.get("workspace_dir"),
            project_id=int(project_id),
        )
    except (RuntimeError, ValueError) as exc:
        return {"error": str(exc)}
    await record_shot_acceptance(
        session,
        contract=contract,
        media_id=int(media_id),
        generation_job_id=int(candidate["job_id"]),
        last_frame_media_id=int(last_frame_media_id),
    )
    return {
        "status": "accepted",
        "shot_number": int(shot_number),
        "media_id": int(media_id),
        "generation_job_id": int(candidate["job_id"]),
        "last_frame_media_id": int(last_frame_media_id),
        "preview": f"![dernière frame du plan {shot_number}](media:{last_frame_media_id})",
    }


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
