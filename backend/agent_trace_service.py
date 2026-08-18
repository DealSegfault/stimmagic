"""Persisted operational traces for the generic agent loop.

The trace is intentionally an execution log, not a dump of private model
reasoning. It keeps the information an engineer needs to inspect and replay a
run: stage, decision summary, tool arguments, references, job/media ids,
validation results, retries, timings and errors.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import re
import uuid
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from database import AgentRun, AgentRunStep

log = get_logger(__name__)

_current_run_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "agent_trace_run_id", default=None
)

_SENSITIVE_KEYS = {
    "api_key", "apikey", "authorization", "cookie", "password", "secret",
    "token", "access_token", "refresh_token", "client_secret",
}
_PRIVATE_REASONING_KEYS = {"thinking", "reasoning", "chain_of_thought", "cot"}
_MAX_TEXT = 16_000
_MAX_ITEMS = 100


def current_agent_run_id() -> Optional[str]:
    """Return the trace id bound to the current agent execution, if any."""
    return _current_run_id.get()


@contextlib.contextmanager
def agent_trace_context(run_id: Optional[str]):
    token = _current_run_id.set(run_id)
    try:
        yield run_id
    finally:
        _current_run_id.reset(token)


def redact_trace_value(value: Any, *, _depth: int = 0) -> Any:
    """Make a JSON-safe, bounded copy suitable for persistence/UI display."""
    if _depth > 5:
        return "[depth limit]"
    if isinstance(value, dict):
        result = {}
        for raw_key, raw_value in list(value.items())[:_MAX_ITEMS]:
            key = str(raw_key)
            lowered = key.casefold()
            if lowered in _SENSITIVE_KEYS:
                result[key] = "[redacted]"
            elif lowered in _PRIVATE_REASONING_KEYS:
                result[key] = "[private reasoning omitted]"
            else:
                result[key] = redact_trace_value(raw_value, _depth=_depth + 1)
        return result
    if isinstance(value, (list, tuple, set)):
        return [redact_trace_value(item, _depth=_depth + 1) for item in list(value)[:_MAX_ITEMS]]
    if isinstance(value, str):
        if len(value) <= _MAX_TEXT:
            return value
        return value[:_MAX_TEXT] + "… [truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:_MAX_TEXT]


def _json_detail(value: Any) -> str:
    return json.dumps(redact_trace_value(value), ensure_ascii=False, default=str)


def _short_summary(value: Any, fallback: str = "") -> str:
    if isinstance(value, dict):
        for key in ("summary", "message", "status", "error", "result"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                value = candidate
                break
    text = str(value or fallback).strip().replace("\n", " ")
    return text[:320] + ("…" if len(text) > 320 else "")


def trace_stage_for_tool(tool_name: str) -> str:
    if tool_name == "get_world_state":
        return "world_state"
    if tool_name in {"view_image", "analyze_image", "browse_web", "web_search"}:
        return "evaluation"
    if tool_name in {"update_world_state", "update_project_scene", "update_project_script", "save_memory"}:
        return "continuity_update"
    if tool_name in {"run_code", "call_tool"}:
        return "generation"
    if tool_name in {"delegate", "stimpack", "skill", "ask_user"}:
        return "orchestration"
    return "tool"


def trace_reference_media_ids(value: Any) -> list[int]:
    """Extract media references from structured tool arguments."""
    ids: list[int] = []
    seen: set[int] = set()

    def visit(node: Any, key: str = "") -> None:
        if isinstance(node, dict):
            for child_key, child in node.items():
                visit(child, str(child_key).casefold())
            return
        if isinstance(node, (list, tuple, set)):
            for child in node:
                visit(child, key)
            return
        if key in {"media_id", "media_ids", "input_images", "reference_media_ids", "selected_media_ids"}:
            try:
                if isinstance(node, str) and not node.strip().isdigit():
                    return
                media_id = int(node)
                if media_id not in seen:
                    seen.add(media_id)
                    ids.append(media_id)
            except (TypeError, ValueError):
                return

    visit(value)
    # Keep the original order: for multimodal generation, Picture 1/2/... is
    # semantic input, not merely an unordered set of media IDs.
    return ids


def trace_action_for_tool(tool_name: str, arguments: Any) -> dict[str, Any]:
    """Describe the operational intent without exposing hidden model reasoning."""
    args = arguments if isinstance(arguments, dict) else {}
    action: dict[str, Any] = {
        "tool": tool_name,
        "kind": "tool_execution",
        "label": f"Execute {tool_name}",
    }
    if tool_name == "get_world_state":
        action.update({
            "kind": "context_resolution",
            "label": "Resolve project World State and canonical references",
        })
    elif tool_name == "skill":
        action.update({
            "kind": "skill_activation",
            "label": f"Activate skill: {args.get('name') or 'unnamed skill'}",
        })
    elif tool_name == "call_tool":
        tool_id = args.get("tool_id") or args.get("name") or "unnamed tool"
        action.update({
            "kind": "tool_execution",
            "label": f"Run generation/tool adapter: {tool_id}",
        })
        inputs = args.get("inputs")
        if isinstance(inputs, dict) and isinstance(inputs.get("prompt"), str):
            action["prompt_preview"] = inputs["prompt"][:600]
    elif tool_name == "run_code":
        code = str(args.get("code") or "")
        lowered = code.casefold()
        action["code_preview"] = code[:600]
        prompt_match = re.search(
            r"\bprompt\s*=\s*(?:'''|\"\"\")(.*?)(?:'''|\"\"\")",
            code,
            re.DOTALL,
        )
        if prompt_match:
            action["prompt_preview"] = prompt_match.group(1).strip()[:600]
        code_reference_ids = [
            int(raw)
            for group in re.findall(r"(?:input_images|input_media_ids)\s*=\s*\[([^\]]+)\]", code)
            for raw in re.findall(r"\d+", group)
        ]
        if code_reference_ids:
            action["reference_media_ids"] = list(dict.fromkeys(code_reference_ids))
        if any(token in lowered for token in ("minimax_h3", "image_to_video", "reference_to_video", "text_to_video")):
            action.update({
                "kind": "video_generation",
                "label": "Generate video with MiniMax H3",
            })
        elif any(token in lowered for token in ("antigravity", "nano banana", "imagegen", "generate_image", "image_generation")):
            action.update({
                "kind": "image_generation",
                "label": "Generate or edit image asset",
            })
        elif any(token in lowered for token in ("view(", "analyze", "inspect", "ffprobe")):
            action.update({
                "kind": "evaluation",
                "label": "Evaluate or inspect generated media",
            })
        else:
            action.update({
                "kind": "python_execution",
                "label": "Execute production Python code",
            })
    elif tool_name in {"view_image", "analyze_image", "browse_web", "web_search"}:
        action.update({
            "kind": "evaluation",
            "label": f"Evaluate reference or result with {tool_name}",
        })
    elif tool_name in {"update_world_state", "update_project_scene", "update_project_script", "save_memory"}:
        action.update({
            "kind": "continuity_update",
            "label": f"Update continuity/project state with {tool_name}",
        })

    reference_ids = trace_reference_media_ids(args)
    if reference_ids:
        action["reference_media_ids"] = reference_ids
    return action


def trace_decision_summary(tool_names: list[str]) -> str:
    """Summarize the observable next action selected by the model."""
    if not tool_names:
        return "Return a user-facing response"
    labels = []
    for tool_name in tool_names:
        labels.append(trace_action_for_tool(tool_name, {})["label"])
    return " → ".join(labels)


def trace_ids_from_value(value: Any) -> tuple[Optional[int], list[int]]:
    """Extract conventional job/media ids from tool output without storing blobs."""
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    job_match = re.search(r"(?:job_id|job)\s*[=:]\s*(\d+)", text, re.IGNORECASE)
    media_ids = [int(raw) for raw in re.findall(r"media_id\s*[=:]\s*(\d+)", text, re.IGNORECASE)]
    return (int(job_match.group(1)) if job_match else None), sorted(set(media_ids))


async def _locked(lock: Any, operation: Callable[[], Awaitable[Any]]) -> Any:
    if lock is None:
        return await operation()
    async with lock:
        return await operation()


async def start_agent_run(
    session: AsyncSession,
    *,
    project_id: Optional[int] = None,
    chat_id: Optional[int] = None,
    workflow: str = "agent_chat",
    mode: str = "trace",
    request_summary: Optional[str] = None,
    ws_manager: Any = None,
) -> Optional[str]:
    """Create a trace row and return its id. Trace failures never block the agent."""
    try:
        run = AgentRun(
            id=str(uuid.uuid4()),
            project_id=project_id,
            chat_id=chat_id,
            workflow=workflow,
            mode=mode,
            status="running",
            request_summary=_short_summary(request_summary),
        )
        session.add(run)
        await session.commit()
        if ws_manager:
            await ws_manager.broadcast("agent_run_started", {"run": run.to_dict(include_request=False)})
        return run.id
    except Exception:
        log.exception("Failed to create agent trace")
        try:
            await session.rollback()
        except Exception:
            pass
        return None


async def start_agent_step(
    session: AsyncSession,
    *,
    stage: str,
    name: str,
    summary: str,
    detail: Any = None,
    tool_call_id: Optional[str] = None,
    attempt: int = 1,
    ws_manager: Any = None,
    session_lock: Any = None,
) -> Optional[int]:
    run_id = current_agent_run_id()
    if not run_id:
        return None

    async def operation():
        result = await session.execute(
            select(func.max(AgentRunStep.sequence)).where(AgentRunStep.run_id == run_id)
        )
        sequence = int(result.scalar() or 0) + 1
        step = AgentRunStep(
            run_id=run_id,
            sequence=sequence,
            stage=stage,
            name=name,
            status="running",
            summary=_short_summary(summary),
            detail=_json_detail(detail or {}),
            tool_call_id=tool_call_id,
            attempt=attempt,
        )
        session.add(step)
        await session.commit()
        if ws_manager:
            await ws_manager.broadcast("agent_run_step", {"run_id": run_id, "step": step.to_dict()})
        return step.id

    try:
        return await _locked(session_lock, operation)
    except Exception:
        log.exception("Failed to start agent trace step %s", name)
        try:
            await session.rollback()
        except Exception:
            pass
        return None


async def finish_agent_step(
    session: AsyncSession,
    step_id: Optional[int],
    *,
    status: str = "completed",
    summary: Optional[str] = None,
    detail: Any = None,
    generation_job_id: Optional[int] = None,
    media_ids: Optional[list[int]] = None,
    ws_manager: Any = None,
    session_lock: Any = None,
) -> None:
    if not step_id:
        return

    async def operation():
        step = await session.get(AgentRunStep, step_id)
        if not step:
            return
        step.status = status
        step.finished_at = datetime.utcnow()
        if summary is not None:
            step.summary = _short_summary(summary)
        if detail is not None:
            try:
                existing_detail = json.loads(step.detail) if step.detail else {}
            except (TypeError, ValueError):
                existing_detail = {}
            if isinstance(existing_detail, dict) and isinstance(detail, dict):
                # Keep the original inputs/reference manifest and layer the
                # completion outcome on top for one inspectable step record.
                step.detail = _json_detail({**existing_detail, **detail})
            else:
                step.detail = _json_detail(detail)
        if generation_job_id is not None:
            step.generation_job_id = generation_job_id
        if media_ids is not None:
            step.media_ids = json.dumps(sorted({int(value) for value in media_ids}))
        await session.commit()
        if ws_manager:
            await ws_manager.broadcast("agent_run_step", {"run_id": step.run_id, "step": step.to_dict()})

    try:
        await _locked(session_lock, operation)
    except Exception:
        log.exception("Failed to finish agent trace step %s", step_id)
        try:
            await session.rollback()
        except Exception:
            pass


async def finish_agent_run(
    session: AsyncSession,
    run_id: Optional[str],
    *,
    status: str,
    summary: Optional[str] = None,
    error: Optional[str] = None,
    ws_manager: Any = None,
) -> None:
    if not run_id:
        return
    try:
        run = await session.get(AgentRun, run_id)
        if not run:
            return
        run.status = status
        run.finished_at = datetime.utcnow()
        if summary is not None:
            run.summary = _short_summary(summary)
        if error is not None:
            run.error = _short_summary(error)
        await session.commit()
        if ws_manager:
            await ws_manager.broadcast("agent_run_finished", {"run": run.to_dict(include_request=False)})
    except Exception:
        log.exception("Failed to finish agent trace %s", run_id)
        try:
            await session.rollback()
        except Exception:
            pass


async def get_agent_run(session: AsyncSession, run_id: str) -> Optional[dict]:
    run = await session.get(AgentRun, run_id)
    if not run:
        return None
    result = await session.execute(
        select(AgentRunStep)
        .where(AgentRunStep.run_id == run_id)
        .order_by(AgentRunStep.sequence.asc(), AgentRunStep.id.asc())
    )
    payload = run.to_dict()
    steps = []
    for step in result.scalars().all():
        step_payload = step.to_dict()
        detail = step_payload.get("detail")
        if isinstance(detail, dict):
            # Enrich historical traces without a data migration.
            if "action" not in detail:
                detail["action"] = trace_action_for_tool(
                    detail.get("tool") or step.name,
                    detail.get("arguments") or {},
                )
            if step.stage == "llm" and "decision_summary" not in detail:
                names = detail.get("tool_names") or []
                if isinstance(names, list):
                    detail["decision_summary"] = trace_decision_summary([str(name) for name in names])
            step_payload["detail"] = detail
        steps.append(step_payload)
    payload["steps"] = steps
    return payload
