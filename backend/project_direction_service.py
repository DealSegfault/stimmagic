"""Project Direction domain service.

This is deliberately built on top of Projects, Boards, Chats and generation
jobs.  Direction owns only the editorial structure and audit trail; artwork
continues to use Stimma's canonical asset/lineage pipeline.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from asset_association_service import attach_asset_to_board_section
from database import (
    Board,
    BoardAssetItem,
    Chat,
    BoardSection,
    GenerationJob,
    ProjectAsset,
    ProjectDirection,
    ProjectDirectionEvent,
    ProjectScene,
)


def json_value(raw: str | None, fallback: Any):
    try:
        value = json.loads(raw) if raw else fallback
        return value if isinstance(value, type(fallback)) else fallback
    except (TypeError, ValueError):
        return fallback


def _normalized_title(value: str | None) -> str:
    """Return a comparison-safe title without changing the displayed title."""
    return re.sub(r"\s+", " ", (value or "").strip().casefold()).strip()


def _legacy_scene_key(scene: ProjectScene) -> str:
    return f"legacy:{scene.sequence_number}:{_normalized_title(scene.title)}"


def _scene_key(scene: ProjectScene) -> str:
    context = json_value(scene.context, {})
    return str(context.get("_script_key") or _legacy_scene_key(scene))


def _parsed_scene_key(item: dict[str, Any]) -> str:
    return str(item.get("source_key") or f"plain:{item.get('sequence_number', 1)}")


def scene_dict(scene: ProjectScene, *, generation_count: int = 0) -> dict[str, Any]:
    return {
        "id": scene.id, "project_id": scene.project_id, "board_id": scene.board_id,
        "sequence_number": scene.sequence_number, "scene_number": scene.scene_number,
        "title": scene.title, "description": scene.description or "", "prompt": scene.prompt or "",
        "context": json_value(scene.context, {}), "dependencies": json_value(scene.dependencies, []),
        "blockers": json_value(scene.blockers, []), "status": scene.status,
        "validation_status": scene.validation_status, "generation_count": generation_count,
        "created_at": scene.created_at.isoformat(), "updated_at": scene.updated_at.isoformat(),
    }


def parse_script(script: str) -> list[dict[str, Any]]:
    """Parse common screenplay/markdown headings without pretending to be an LLM.

    Explicit headings win.  Markdown shot maps are also common in imported
    scripts: when the document repeats its shot-table header, each table is a
    scene-sized section.  A script with no structural markers becomes one
    reviewable scene instead of silently dropping a user's text.
    """
    text = script.strip()
    if not text:
        return []
    lines = text.splitlines()
    scenes: list[dict[str, Any]] = []
    sequence = 1
    current: dict[str, Any] | None = None
    pending_prefix: list[str] = []
    sequence_re = re.compile(
        r"^\s*(?:#+\s*)?(?:sequence|séquence)\b"
        r"\s*(\d+)?\s*(?:[-:–—.]\s*)?(.*?)\s*$",
        re.I,
    )
    scene_re = re.compile(
        r"^\s*(?:#+\s*)?(?:scene|sc[eè]ne)\b"
        r"\s*(\d+)?\s*(?:[-:–—.]\s*)?(.*?)\s*$",
        re.I,
    )
    slug_re = re.compile(r"^\s*(?:INT\.|EXT\.|INT/EXT\.|I/E\.)\s+", re.I)

    # A shot-map export can omit sequence/scene headings while still
    # delimiting sections with the repeated table header.  Only use this
    # fallback when the header occurs more than once so ordinary markdown
    # tables remain part of the current scene.
    shot_table_re = re.compile(
        r"^\s*\|\s*#\s*\|\s*(?:durée|duration)\b.*\|\s*$",
        re.I,
    )
    has_explicit_scenes = any(scene_re.match(line) or slug_re.match(line) for line in lines)
    sequence_matches = [sequence_re.match(line) for line in lines]
    has_multiple_sequences = sum(bool(match) for match in sequence_matches) > 1
    shot_table_indexes = [index for index, line in enumerate(lines) if shot_table_re.match(line)]
    has_multiple_shot_tables = len(shot_table_indexes) > 1

    def finish() -> None:
        nonlocal current
        if current is None:
            return
        current["description"] = "\n".join(current.pop("body")).strip()
        scenes.append(current)
        current = None

    def start(title: str, sequence_number: int, source_key: str | None = None) -> None:
        nonlocal current, pending_prefix, sequence
        if current is not None:
            finish()
        sequence = sequence_number
        current = {
            "sequence_number": sequence_number,
            "title": title or f"Scene {len(scenes) + 1}",
            "source_key": source_key or f"title:{sequence_number}:{_normalized_title(title)}",
            "body": pending_prefix,
        }
        pending_prefix = []

    for line in lines:
        sequence_match = sequence_re.match(line)
        if sequence_match:
            number = int(sequence_match.group(1)) if sequence_match.group(1) else sequence + (1 if current else 0)
            title = sequence_match.group(2).strip() or f"Sequence {number}"
            if not has_explicit_scenes and has_multiple_sequences:
                start(title, number, f"sequence:{number}")
            else:
                sequence = number
            continue

        scene_match = scene_re.match(line)
        if scene_match or slug_re.match(line):
            title = (scene_match.group(2).strip() if scene_match else line.strip()) if scene_match else line.strip()
            explicit_number = int(scene_match.group(1)) if scene_match and scene_match.group(1) else None
            source_key = (
                f"scene:{sequence}:{explicit_number}"
                if explicit_number is not None
                else f"title:{sequence}:{_normalized_title(title)}"
            )
            if not scene_match:
                source_key = f"slug:{sequence}:{_normalized_title(title)}"
            start(title, sequence, source_key)
            continue

        if has_multiple_shot_tables and shot_table_re.match(line) and not has_explicit_scenes and not has_multiple_sequences:
            next_scene_number = len(scenes) + (2 if current is not None else 1)
            start(f"Scene {next_scene_number}", next_scene_number, f"shot:{next_scene_number}")

        if current is None:
            pending_prefix.append(line)
        else:
            current["body"].append(line)

    if current is None:
        current = {"sequence_number": sequence, "title": "Scene 1", "source_key": "plain:1", "body": pending_prefix}
    finish()
    return scenes


async def record_event(session: AsyncSession, project_id: int, kind: str, *, actor: str = "user", scene_id: int | None = None, chat_id: int | None = None, generation_job_id: int | None = None, payload: dict | None = None) -> None:
    session.add(ProjectDirectionEvent(project_id=project_id, scene_id=scene_id, chat_id=chat_id, generation_job_id=generation_job_id, kind=kind, actor=actor, payload=json.dumps(payload or {})))


async def direction_payload(session: AsyncSession, project_id: int) -> dict[str, Any]:
    direction = await session.get(ProjectDirection, project_id)
    scenes = (await session.execute(select(ProjectScene).where(ProjectScene.project_id == project_id).order_by(ProjectScene.sequence_number, ProjectScene.scene_number))).scalars().all()
    jobs = (await session.execute(select(GenerationJob).where(GenerationJob.project_id == project_id))).scalars().all()
    by_scene: dict[int, int] = {}
    for job in jobs:
        params = json_value(job.parameters, {})
        scene_id = params.get("_direction_scene_id")
        if isinstance(scene_id, int): by_scene[scene_id] = by_scene.get(scene_id, 0) + 1
    return {
        "script_name": direction.script_name if direction else None,
        "script_text": direction.script_text if direction else "",
        "summary": direction.summary if direction else "",
        "context": json_value(direction.context if direction else None, {}),
        "scenes": [scene_dict(scene, generation_count=by_scene.get(scene.id, 0)) for scene in scenes],
        "progress": {"total": len(scenes), "validated": sum(s.validation_status == "approved" for s in scenes), "blocked": sum(bool(json_value(s.blockers, [])) for s in scenes), "generated": sum(by_scene.values())},
    }


async def _sync_scene_chat_contexts(
    session: AsyncSession,
    scene: ProjectScene,
    *,
    removed: bool = False,
) -> list[int]:
    """Keep scene-chat instructions aligned with the canonical scene row."""
    events = (await session.execute(
        select(ProjectDirectionEvent)
        .where(
            ProjectDirectionEvent.project_id == scene.project_id,
            ProjectDirectionEvent.scene_id == scene.id,
            ProjectDirectionEvent.chat_id.is_not(None),
            ProjectDirectionEvent.kind == "scene_chat_created",
        )
        .order_by(ProjectDirectionEvent.created_at.desc(), ProjectDirectionEvent.id.desc())
    )).scalars().all()
    chat_ids = list(dict.fromkeys(event.chat_id for event in events if event.chat_id is not None))
    updated_chat_ids: list[int] = []
    for chat_id in chat_ids:
        chat = await session.get(Chat, chat_id)
        raw_instructions = chat.additional_instructions if chat else ""
        if not chat or not raw_instructions or "DIRECTION_CONTEXT=" not in raw_instructions:
            continue
        prefix, encoded_context = raw_instructions.split("DIRECTION_CONTEXT=", 1)
        try:
            scene_context = json.loads(encoded_context)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(scene_context, dict):
            continue
        scene_context.update({
            "scene_id": scene.id,
            "sequence": scene.sequence_number,
            "scene": scene.scene_number,
            "title": scene.title,
            "description": scene.description or "",
            "prompt": scene.prompt or "",
            "board_id": scene.board_id,
            "dependencies": json_value(scene.dependencies, []),
            "blockers": json_value(scene.blockers, []),
            "status": scene.status,
            "validation_status": scene.validation_status,
            "script_removed": removed,
        })
        chat.additional_instructions = prefix + "DIRECTION_CONTEXT=" + json.dumps(scene_context, ensure_ascii=False)
        updated_chat_ids.append(chat.id)
    return updated_chat_ids


async def reconcile_script(
    session: AsyncSession,
    project_id: int,
    script: str,
    script_name: str | None,
    summary: str | None,
    context: dict | None,
    *,
    actor: str = "user",
    event_kind: str = "script_imported",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Replace the canonical script and cascade its structural consequences.

    Scene identity is based on parser source keys whenever available, with a
    same-length positional fallback for legacy imports that predate source
    keys. This keeps boards, generation history and scene chats attached while
    allowing insertions, removals and reordering in later script revisions.
    """
    parsed = parse_script(script)
    if not parsed:
        raise ValueError("The script is empty")
    direction = await session.get(ProjectDirection, project_id)
    old_scenes = []
    if direction is None:
        direction = ProjectDirection(project_id=project_id, script_name=script_name, script_text=script, summary=summary, context=json.dumps(context or {}))
        session.add(direction)
    else:
        direction.script_name, direction.script_text, direction.summary = script_name, script, summary
        direction.context, direction.updated_at = json.dumps(context or {}), datetime.utcnow()
        old_scenes = (await session.execute(
            select(ProjectScene)
            .where(ProjectScene.project_id == project_id)
            .order_by(ProjectScene.sequence_number, ProjectScene.scene_number, ProjectScene.id)
        )).scalars().all()

    project_asset_ids = list(await session.scalars(
        select(ProjectAsset.asset_id)
        .where(ProjectAsset.project_id == project_id, ProjectAsset.deleted_at.is_(None))
        .order_by(ProjectAsset.added_at, ProjectAsset.asset_id)
    ))
    used_board_ids: set[int] = set()
    used_scene_ids: set[int] = set()
    active_scenes: list[ProjectScene] = []
    changed_scene_ids: list[int] = []
    created_scene_ids: list[int] = []
    updated_board_ids: list[int] = []
    created_board_ids: list[int] = []
    removed_board_ids: list[int] = []
    removed_scene_ids: list[int] = []
    updated_chat_ids: list[int] = []

    old_by_key: dict[str, list[ProjectScene]] = {}
    for old_scene in old_scenes:
        old_by_key.setdefault(_scene_key(old_scene), []).append(old_scene)
    legacy_import = bool(old_scenes) and all(
        "_script_key" not in json_value(old_scene.context, {})
        for old_scene in old_scenes
    )

    def take_by_key(key: str) -> ProjectScene | None:
        candidates = old_by_key.get(key, [])
        while candidates:
            candidate = candidates.pop(0)
            if candidate.id not in used_scene_ids:
                return candidate
        return None

    for index, item in enumerate(parsed, start=1):
        scene = take_by_key(_parsed_scene_key(item))
        # Existing imports had no source key. When the number of scenes is
        # unchanged, positional matching preserves a scene whose heading was
        # renamed without making a new board.
        if scene is None and legacy_import and len(parsed) == len(old_scenes) and index <= len(old_scenes):
            candidate = old_scenes[index - 1]
            if candidate.id not in used_scene_ids:
                scene = candidate
        is_new_scene = scene is None
        board = await session.get(Board, scene.board_id) if scene and scene.board_id else None
        if board is None or board.id in used_board_ids or board.deleted_at is not None:
            board = Board(name="", project_id=project_id)
            session.add(board)
            await session.flush()
            created_board_ids.append(board.id)
        board.name = f"S{item['sequence_number']:02d} · {item['title']}"
        board.project_id = project_id
        board.deleted_at = None
        board.updated_at = datetime.utcnow()
        used_board_ids.add(board.id)
        updated_board_ids.append(board.id)

        scene = scene or ProjectScene(project_id=project_id)
        previous_title = scene.title if not is_new_scene else None
        previous_description = scene.description if not is_new_scene else None
        used_scene_ids.add(scene.id) if scene.id is not None else None
        scene.board_id = board.id
        scene.sequence_number = item["sequence_number"]
        scene.scene_number = index
        scene.title = item["title"]
        scene.description = item["description"]
        scene.prompt = item["description"]
        if (
            not is_new_scene
            and (previous_title != scene.title or previous_description != scene.description)
            and scene.validation_status == "approved"
        ):
            scene.validation_status = "pending"
            if scene.status == "complete":
                scene.status = "planned"
        scene_context = json_value(scene.context, {})
        scene_context["_script_key"] = _parsed_scene_key(item)
        scene.context = json.dumps(scene_context, ensure_ascii=False)
        if scene.dependencies is None:
            scene.dependencies = json.dumps([])
        if scene.blockers is None:
            scene.blockers = json.dumps([])
        session.add(scene)
        await session.flush()
        used_scene_ids.add(scene.id)
        active_scenes.append(scene)
        changed_scene_ids.append(scene.id)
        if is_new_scene:
            created_scene_ids.append(scene.id)
        updated_chat_ids.extend(await _sync_scene_chat_contexts(session, scene))

        sections = (await session.execute(
            select(BoardSection)
            .where(BoardSection.board_id == board.id, BoardSection.deleted_at.is_(None))
            .order_by(BoardSection.display_order, BoardSection.id)
        )).scalars().all()
        sections_by_name = {section.name: section for section in sections if section.name}
        if "References" not in sections_by_name:
            default_section = next((section for section in sections if section.is_default), None)
            if default_section is not None:
                default_section.name = "References"
                sections_by_name["References"] = default_section
        for order, name in enumerate(("References", "Variants", "Approved")):
            if name not in sections_by_name:
                section = BoardSection(board_id=board.id, name=name, is_default=order == 0, display_order=order)
                session.add(section)
                sections_by_name[name] = section
        await session.flush()

        # Project references are shared creative context, so seed them into
        # every scene board's References section. Generated variants remain
        # empty until the scene is worked on.
        references = sections_by_name["References"]
        existing_asset_ids = set(await session.scalars(
            select(BoardAssetItem.asset_id).where(
                BoardAssetItem.board_section_id == references.id,
                BoardAssetItem.deleted_at.is_(None),
            )
        ))
        next_order = await session.scalar(
            select(func.coalesce(func.max(BoardAssetItem.display_order), -1)).where(
                BoardAssetItem.board_section_id == references.id,
                BoardAssetItem.deleted_at.is_(None),
            )
        )
        for asset_id in project_asset_ids:
            if asset_id in existing_asset_ids:
                continue
            _, added = await attach_asset_to_board_section(
                session,
                board=board,
                section_id=references.id,
                asset_id=asset_id,
                display_order=(next_order or -1) + 1,
            )
            if added:
                existing_asset_ids.add(asset_id)
                next_order = (next_order or -1) + 1

    for stale_scene in old_scenes:
        if stale_scene.id in used_scene_ids:
            continue
        if stale_scene.board_id and stale_scene.board_id not in used_board_ids:
            stale_board = await session.get(Board, stale_scene.board_id)
            if stale_board is not None:
                stale_board.deleted_at = datetime.utcnow()
                stale_board.updated_at = datetime.utcnow()
                removed_board_ids.append(stale_board.id)
        updated_chat_ids.extend(await _sync_scene_chat_contexts(session, stale_scene, removed=True))
        await record_event(
            session,
            project_id,
            "script_scene_removed",
            actor=actor,
            scene_id=stale_scene.id,
            payload={"title": stale_scene.title, "board_id": stale_scene.board_id},
        )
        removed_scene_ids.append(stale_scene.id)
        await session.delete(stale_scene)

    removed_ids = set(removed_scene_ids)
    for scene in active_scenes:
        dependencies = json_value(scene.dependencies, [])
        filtered_dependencies = [
            dependency
            for dependency in dependencies
            if not (
                (isinstance(dependency, int) and dependency in removed_ids)
                or (isinstance(dependency, str) and dependency.isdigit() and int(dependency) in removed_ids)
            )
        ]
        if filtered_dependencies != dependencies:
            scene.dependencies = json.dumps(filtered_dependencies, ensure_ascii=False)
            updated_chat_ids.extend(await _sync_scene_chat_contexts(session, scene))
    await record_event(
        session,
        project_id,
        event_kind,
        actor=actor,
        payload={
            "script_name": script_name,
            "scene_count": len(parsed),
            "created_scene_ids": created_scene_ids,
            "updated_scene_ids": changed_scene_ids,
            "removed_scene_ids": removed_scene_ids,
            "updated_board_ids": sorted(set(updated_board_ids)),
            "removed_board_ids": sorted(set(removed_board_ids)),
        },
    )
    await session.flush()
    return await direction_payload(session, project_id), {
        "scene_ids": sorted(set(changed_scene_ids)),
        "created_scene_ids": created_scene_ids,
        "removed_scene_ids": removed_scene_ids,
        "board_ids": sorted(set(updated_board_ids)),
        "created_board_ids": created_board_ids,
        "removed_board_ids": sorted(set(removed_board_ids)),
        "chat_ids": sorted(set(updated_chat_ids)),
    }


async def import_script(session: AsyncSession, project_id: int, script: str, script_name: str | None, summary: str | None, context: dict | None) -> dict[str, Any]:
    payload, _ = await reconcile_script(
        session,
        project_id,
        script,
        script_name,
        summary,
        context,
        actor="user",
        event_kind="script_imported",
    )
    return payload
