"""Agent primitives for the Project Direction workspace."""
import json
from sqlalchemy import select

from ..tools_registry import ToolParameter, tool
from database import Board, ProjectDirection, ProjectScene
from project_direction_service import (
    _sync_scene_chat_contexts,
    direction_payload,
    json_value,
    reconcile_script,
    record_event,
)
from utils.websocket import ws_manager


@tool(name="get_project_direction", description="Read the project's script, ordered scenes, boards, blockers, validation and generation progress. Use it before planning or generating scene work.", parameters=[], scope="agent")
async def get_project_direction(**kwargs) -> dict:
    session = kwargs.get("session"); project_id = kwargs.get("project_id")
    if not session or not project_id: return {"error": "This chat is not attached to a project."}
    payload = await direction_payload(session, project_id)
    await record_event(session, project_id, "agent_direction_read", actor="agent")
    await session.commit()
    return payload


@tool(name="update_project_scene", description="Record an editorial change, blocker, status or validation on a Direction scene. This is the canonical project record, not a private chat note.", parameters=[ToolParameter(name="scene_id", type="integer", description="Direction scene id"), ToolParameter(name="status", type="string", description="planned, in_progress, ready_for_review, complete", required=False), ToolParameter(name="validation_status", type="string", description="pending, approved, changes_requested", required=False), ToolParameter(name="blockers", type="array", description="Current blocking issues", required=False, items={"type": "string"}), ToolParameter(name="prompt", type="string", description="Approved generation prompt", required=False)], scope="agent")
async def update_project_scene(scene_id: int, status: str | None = None, validation_status: str | None = None, blockers: list | None = None, prompt: str | None = None, **kwargs) -> dict:
    session = kwargs.get("session"); project_id = kwargs.get("project_id")
    if not session or not project_id: return {"error": "This chat is not attached to a project."}
    scene = await session.scalar(select(ProjectScene).where(ProjectScene.id == scene_id, ProjectScene.project_id == project_id))
    if not scene: return {"error": f"Scene {scene_id} was not found in this project."}
    changed = {}
    for key, value in (("status", status), ("validation_status", validation_status), ("prompt", prompt)):
        if value is not None: setattr(scene, key, value); changed[key] = value
    if blockers is not None: scene.blockers = json.dumps(blockers); changed["blockers"] = blockers
    if scene.board_id:
        board = await session.get(Board, scene.board_id)
        if board:
            from datetime import datetime
            board.updated_at = datetime.utcnow()
    await _sync_scene_chat_contexts(session, scene)
    await record_event(session, project_id, "agent_scene_updated", actor="agent", scene_id=scene.id, payload=changed)
    await session.commit()
    await ws_manager.broadcast("project_direction_updated", {
        "project_id": project_id,
        "scene_id": scene.id,
        "scene_ids": [scene.id],
        "board_ids": [scene.board_id] if scene.board_id else [],
    })
    return {"scene_id": scene.id, "updated": changed, "board_id": scene.board_id}


@tool(
    name="update_project_script",
    description=(
        "Replace the project's canonical script after a user asks to change it. "
        "Always call get_project_direction first, apply the requested edit to the full script, "
        "then pass the complete replacement here. This cascades scene identity, ordering, "
        "scene descriptions/prompts, linked boards, scene-chat context and removal of deleted "
        "scenes while preserving matching boards and generation history. Never keep a script "
        "edit only in chat text or a workspace file."
    ),
    parameters=[
        ToolParameter(name="script", type="string", description="The complete updated script, not a diff."),
        ToolParameter(name="script_name", type="string", description="Optional script name; omit to keep the current name.", required=False),
        ToolParameter(name="summary", type="string", description="Optional updated project summary; omit to keep the current summary.", required=False),
        ToolParameter(name="context", type="object", description="Optional global creative constraints; omit to keep the current context.", required=False),
    ],
    scope="agent",
)
async def update_project_script(script: str, script_name: str | None = None, summary: str | None = None, context: dict | None = None, **kwargs) -> dict:
    session = kwargs.get("session")
    project_id = kwargs.get("project_id")
    if not session or not project_id:
        return {"error": "This chat is not attached to a project."}
    if not script or not script.strip():
        return {"error": "The replacement script is empty."}

    current = await session.get(ProjectDirection, project_id)
    if current:
        script_name = current.script_name if script_name is None else script_name
        summary = current.summary if summary is None else summary
        context = json_value(current.context, {}) if context is None else context

    try:
        payload, change = await reconcile_script(
            session,
            project_id,
            script,
            script_name,
            summary,
            context,
            actor="agent",
            event_kind="script_updated_by_agent",
        )
        await session.commit()
    except ValueError as exc:
        return {"error": str(exc)}

    await ws_manager.broadcast("project_direction_updated", {"project_id": project_id, **change})
    return {
        "updated": True,
        "script_name": payload.get("script_name"),
        "scenes": len(payload.get("scenes", [])),
        "scenes_created": len(change.get("created_scene_ids", [])),
        "scenes_updated": len(change.get("scene_ids", [])),
        "scenes_removed": len(change.get("removed_scene_ids", [])),
        "boards_updated": len(change.get("board_ids", [])),
        "boards_created": len(change.get("created_board_ids", [])),
        "boards_removed": len(change.get("removed_board_ids", [])),
        "scene_chat_contexts_updated": len(change.get("chat_ids", [])),
        "direction": {
            "progress": payload.get("progress", {}),
            "scenes": [
                {key: scene.get(key) for key in ("id", "sequence_number", "scene_number", "title", "board_id")}
                for scene in payload.get("scenes", [])
            ],
        },
    }
