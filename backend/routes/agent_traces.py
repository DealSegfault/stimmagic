"""Read-only API for generic agent execution traces."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_trace_service import get_agent_run
from core.dependencies import get_db_session
from database import AgentRun, AgentRunStep

router = APIRouter(tags=["agent-traces"])


@router.get("/api/chats/{chat_id}/agent-runs")
async def list_chat_agent_runs(
    chat_id: int,
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
):
    result = await session.execute(
        select(AgentRun, func.count(AgentRunStep.id))
        .outerjoin(AgentRunStep, AgentRunStep.run_id == AgentRun.id)
        .where(AgentRun.chat_id == chat_id)
        .group_by(AgentRun.id)
        .order_by(desc(AgentRun.started_at))
        .limit(limit)
    )
    return {"items": [_run_summary(run, step_count) for run, step_count in result.all()]}


@router.get("/api/projects/{project_id}/agent-runs")
async def list_project_agent_runs(
    project_id: int,
    scene_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
):
    # Scene-level filtering is intentionally deferred to scene envelopes in
    # the trace details; project filtering remains generic for all projects.
    query = (
        select(AgentRun, func.count(AgentRunStep.id))
        .outerjoin(AgentRunStep, AgentRunStep.run_id == AgentRun.id)
        .where(AgentRun.project_id == project_id)
        .group_by(AgentRun.id)
        .order_by(desc(AgentRun.started_at))
        .limit(limit)
    )
    result = await session.execute(query)
    return {"items": [_run_summary(run, step_count) for run, step_count in result.all()]}


@router.get("/api/agent-runs/{run_id}")
async def get_agent_run_detail(
    run_id: str,
    session: AsyncSession = Depends(get_db_session),
):
    payload = await get_agent_run(session, run_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return payload


def _run_summary(run: AgentRun, step_count: int) -> dict:
    payload = run.to_dict(include_request=True)
    payload["step_count"] = int(step_count)
    return payload
