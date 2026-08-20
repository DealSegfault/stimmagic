import json
from datetime import datetime

import pytest
from sqlalchemy import select

from database import GenerationJob, Project, ProjectScene, ProjectShot
from production_service import list_shot_candidates
from tests.helpers.media import create_media_item


@pytest.mark.asyncio
async def test_imported_sequence_has_canonical_shot(client, db_session):
    project = (
        await client.post("/api/projects", json={"name": "Production test"})
    ).json()
    project_id = project["id"]
    response = await client.post(
        f"/api/projects/{project_id}/direction/import",
        json={"script": "SEQUENCE 1 — Cuisine\nUne personne entre."},
    )
    assert response.status_code == 200, response.text
    production = await client.get(f"/api/projects/{project_id}/production")
    assert production.status_code == 200, production.text
    payload = production.json()
    assert payload["stats"]["sequence_count"] == 1
    assert payload["stats"]["shot_count"] == 1
    shot = payload["sequences"][0]["shots"][0]
    assert shot["shot_number"] == 1
    assert shot["transition_policy"] == "continuity"
    assert shot["blocking"]["location"]["label"]
    assert len(shot["blocking"]["frames"]) == 4
    assert shot["blocking"]["frames"][0]["time_start"] == 0.0
    assert shot["blocking"]["frames"][-1]["time_end"] == 4.0
    assert all(
        frame["time_end"] - frame["time_start"] <= 1.0
        for frame in shot["blocking"]["frames"]
    )
    assert all(frame["performance_note"] for frame in shot["blocking"]["frames"])
    assert shot["blocking"]["camera"]["distance_meters"] > 0


@pytest.mark.asyncio
async def test_imported_shot_table_creates_each_plan(client):
    project = (
        await client.post("/api/projects", json={"name": "Shot map production"})
    ).json()
    response = await client.post(
        f"/api/projects/{project['id']}/direction/import",
        json={
            "script": """# SÉQUENCE 1 — Cuisine
| # | Durée | Code | Plan — texte intégral | Raccord entrant exact |
|---|---:|---|---|---|
| **01** | 4 s | **A** | Maya verse le thé. | Début |
| **02** | 6 s | **B** | Maya regarde la porte. | Réaction |
"""
        },
    )
    assert response.status_code == 200, response.text
    production = await client.get(f"/api/projects/{project['id']}/production")
    shots = production.json()["sequences"][0]["shots"]
    assert [shot["shot_number"] for shot in shots] == [1, 2]
    assert [shot["duration"] for shot in shots] == [4.0, 6.0]
    assert all(shot["transition_policy"] == "independent" for shot in shots)
    assert all(shot["blocking"]["source"] == "script-inference" for shot in shots)
    assert sum(len(shot["blocking"]["frames"]) for shot in shots) == 10


@pytest.mark.asyncio
async def test_blocking_keeps_last_actor_position_across_insert(client):
    project = (
        await client.post("/api/projects", json={"name": "Blocking continuity"})
    ).json()
    response = await client.post(
        f"/api/projects/{project['id']}/direction/import",
        json={
            "script": """# SÉQUENCE 1 — Appartement
| # | Durée | Code | Plan — texte intégral | Raccord entrant exact |
|---|---:|---|---|---|
| **01** | 4 s | **A** | Maya avance vers la porte. | Début |
| **02** | 2 s | **B** | Insert gros plan sur la poignée. | Raccord regard |
| **03** | 3 s | **C** | Retour Maya devant la porte. Elle se fige. | Même position |
"""
        },
    )
    assert response.status_code == 200, response.text
    production = await client.get(f"/api/projects/{project['id']}/production")
    shots = production.json()["sequences"][0]["shots"]
    first_actor = shots[0]["blocking"]["frames"][-1]["actors"][0]
    third_actor = shots[2]["blocking"]["frames"][0]["actors"][0]
    assert shots[1]["blocking"]["continuity"]["verdict"] == "cutaway"
    assert abs(first_actor["x"] - third_actor["x"]) < 1
    assert abs(first_actor["y"] - third_actor["y"]) < 1


@pytest.mark.asyncio
async def test_approved_blocking_is_persisted_and_counted(client):
    project = (
        await client.post("/api/projects", json={"name": "Blocking review"})
    ).json()
    imported = await client.post(
        f"/api/projects/{project['id']}/direction/import",
        json={"script": "SCÈNE 1 — Salon\nMaya regarde la porte."},
    )
    assert imported.status_code == 200, imported.text
    first_payload = (
        await client.get(f"/api/projects/{project['id']}/production")
    ).json()
    shot = first_payload["sequences"][0]["shots"][0]
    approved_blocking = {
        **shot["blocking"],
        "status": "approved",
        "reviewed_at": "2026-08-20T12:00:00Z",
    }
    updated = await client.patch(
        f"/api/projects/{project['id']}/production/shots/{shot['id']}",
        json={
            "settings": {**shot["settings"], "blocking": approved_blocking},
            "revision": shot["revision"],
        },
    )
    assert updated.status_code == 200, updated.text
    reviewed_payload = (
        await client.get(f"/api/projects/{project['id']}/production")
    ).json()
    reviewed_shot = reviewed_payload["sequences"][0]["shots"][0]
    assert reviewed_shot["blocking"]["status"] == "approved"
    assert reviewed_payload["stats"]["blocking_reviewed_count"] == 1


@pytest.mark.asyncio
async def test_blocking_supports_multiple_character_instances(client):
    project = (
        await client.post("/api/projects", json={"name": "Multiple Mayas"})
    ).json()
    imported = await client.post(
        f"/api/projects/{project['id']}/direction/import",
        json={
            "script": (
                "SCÈNE 1 — Bureau\n"
                "Maya principale reste dans le salon. Une TROISIÈME MAYA est immobile dans le bureau."
            )
        },
    )
    assert imported.status_code == 200, imported.text
    payload = (await client.get(f"/api/projects/{project['id']}/production")).json()
    actors = payload["sequences"][0]["shots"][0]["blocking"]["frames"][0]["actors"]
    relationships = payload["sequences"][0]["shots"][0]["blocking"]["frames"][0][
        "relationships"
    ]
    assert [actor["id"] for actor in actors] == ["maya", "maya_3"]
    assert actors[0]["x"] != actors[1]["x"] or actors[0]["y"] != actors[1]["y"]
    assert relationships[0]["from"] == "Maya"
    assert relationships[0]["to"] == "Troisième Maya"
    assert relationships[0]["distance_meters"] > 0


@pytest.mark.asyncio
async def test_scene_recent_candidate_cannot_be_approved(db_session):
    async with db_session() as session:
        project = Project(name="Production candidates")
        session.add(project)
        await session.flush()
        scene = ProjectScene(
            project_id=project.id,
            sequence_number=1,
            scene_number=1,
            title="Kitchen",
            description="A scene",
        )
        session.add(scene)
        await session.flush()
        shot = ProjectShot(
            project_id=project.id,
            scene_id=scene.id,
            shot_number=1,
            source_key="test:scene:1:shot:1",
            title="Plan 1",
        )
        session.add(shot)
        media = await create_media_item(
            session,
            file_path="/production/candidate.mp4",
            file_format="mp4",
            duration=4,
        )
        session.add(
            GenerationJob(
                status="completed",
                task_type="image-to-video",
                generator_type="test",
                generator_name="test",
                model_name="test",
                parameters=json.dumps({"_direction_scene_id": scene.id}),
                folder_path="/production",
                project_id=project.id,
                result_media_id=media.id,
                completed_at=datetime.utcnow(),
            )
        )
        await session.commit()
        shot_id = shot.id
    async with db_session() as session:
        row = await session.get(ProjectShot, shot_id)
        candidates = await list_shot_candidates(session, row)
        exact_candidates = await list_shot_candidates(
            session, row, include_scene_fallback=False
        )
    assert candidates[0]["match_confidence"] == "scene_recent"
    assert candidates[0]["approval_eligible"] is False
    assert exact_candidates == []
