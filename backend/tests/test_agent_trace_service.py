import json

import pytest

from agent_trace_service import (
    agent_trace_context,
    finish_agent_run,
    finish_agent_step,
    get_agent_run,
    redact_trace_value,
    start_agent_run,
    start_agent_step,
    trace_action_for_tool,
    trace_decision_summary,
)
from database import Chat, Project


def test_trace_redaction_omits_private_reasoning_and_secrets():
    value = redact_trace_value({
        "prompt": "keep this prompt",
        "api_key": "secret",
        "thinking": "private chain of thought",
        "nested": {"token": "also secret"},
    })
    assert value["prompt"] == "keep this prompt"
    assert value["api_key"] == "[redacted]"
    assert value["thinking"] == "[private reasoning omitted]"
    assert value["nested"]["token"] == "[redacted]"


def test_trace_describes_generation_intent_and_references():
    action = trace_action_for_tool(
        "run_code",
        {"code": "from stimma.tools.reference_to_video import minimax_h3_r2v", "input_images": [152, 147]},
    )
    assert action["kind"] == "video_generation"
    assert action["reference_media_ids"] == [152, 147]
    assert trace_decision_summary(["get_world_state", "run_code"]).startswith("Resolve project World State")


@pytest.mark.asyncio
async def test_agent_run_persists_ordered_operational_steps(db_session):
    async with db_session() as session:
        project = Project(name="Trace project")
        session.add(project)
        await session.flush()
        chat = Chat(name="Trace chat", project_id=project.id)
        session.add(chat)
        await session.commit()

        run_id = await start_agent_run(
            session,
            project_id=project.id,
            chat_id=chat.id,
            request_summary="Generate the next shot",
        )
        assert run_id

        with agent_trace_context(run_id):
            first = await start_agent_step(
                session,
                stage="world_state",
                name="get_world_state",
                summary="Resolve canonical project references",
                detail={"reference_ids": ["@loc_demo"]},
            )
            await finish_agent_step(
                session,
                first,
                summary="World state loaded",
                detail={"reference_count": 1},
            )
            second = await start_agent_step(
                session,
                stage="generation",
                name="run_code",
                summary="Generate candidate keyframe",
                detail={"prompt": "a cinematic kitchen insert"},
            )
            await finish_agent_step(
                session,
                second,
                generation_job_id=42,
                media_ids=[101, 101],
                summary="Candidate generated",
                detail={"result": "job_id=42 media_id=101"},
            )

        await finish_agent_run(session, run_id, status="completed", summary="Agent loop finished")

    async with db_session() as session:
        payload = await get_agent_run(session, run_id)
        assert payload["status"] == "completed"
        assert [step["sequence"] for step in payload["steps"]] == [1, 2]
        assert payload["steps"][1]["generation_job_id"] == 42
        assert payload["steps"][1]["media_ids"] == [101]
        assert payload["steps"][0]["detail"]["reference_ids"] == ["@loc_demo"]


@pytest.mark.asyncio
async def test_agent_run_routes_list_and_detail(client, db_session):
    async with db_session() as session:
        project = Project(name="Route trace project")
        session.add(project)
        await session.flush()
        chat = Chat(name="Route trace chat", project_id=project.id)
        session.add(chat)
        await session.commit()
        project_id, chat_id = project.id, chat.id

        run_id = await start_agent_run(session, project_id=project_id, chat_id=chat_id, request_summary="route")
        with agent_trace_context(run_id):
            step_id = await start_agent_step(
                session,
                stage="evaluation",
                name="view_image",
                summary="Inspect reference image",
            )
            await finish_agent_step(session, step_id, summary="Reference inspected")
        await finish_agent_run(session, run_id, status="completed")

    response = await client.get(f"/api/chats/{chat_id}/agent-runs")
    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == run_id

    response = await client.get(f"/api/agent-runs/{run_id}")
    assert response.status_code == 200
    assert response.json()["steps"][0]["name"] == "view_image"

    response = await client.get(f"/api/projects/{project_id}/agent-runs")
    assert response.status_code == 200
    assert response.json()["items"][0]["chat_id"] == chat_id
