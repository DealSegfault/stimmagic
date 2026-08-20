from pathlib import Path

import pytest
from sqlalchemy import select

from database import (
    Project,
    ProjectCompositionItem,
    ProjectElement,
    ProjectReferencePack,
    ProjectReferenceView,
)
from project_element_service import create_project_element
from reference_generation_service import (
    build_composition_generation_request,
    build_view_generation_request,
)
from reference_service import create_composition, ensure_reference_pack
from tests.helpers.media import create_media_item


@pytest.mark.asyncio
async def test_reference_api_creates_assetless_prop_with_canonical_slots(client, db_session):
    project = (await client.post("/api/projects", json={"name": "Reference lab"})).json()

    created = await client.post(
        f"/api/projects/{project['id']}/elements",
        json={"element_type": "prop"},
    )
    assert created.status_code == 200, created.text
    element = created.json()
    assert element["name"] == "Untitled prop 1"
    assert element["asset_id"] is None

    workspace = await client.get(f"/api/projects/{project['id']}/references")
    assert workspace.status_code == 200, workspace.text
    pack = workspace.json()["packs"][0]
    assert [view["view_key"] for view in pack["views"]] == [
        "hero_3q", "front", "left", "right", "back", "top",
    ]
    assert all(view["status"] == "missing" for view in pack["views"])
    stable_reference = pack["element"]["reference_id"]

    state = await client.post(
        f"/api/projects/{project['id']}/references/packs/{pack['id']}/states",
        json={"state_key": "", "label": "Éteinte", "prompt_delta": "Aucune émission lumineuse."},
    )
    assert state.status_code == 200, state.text
    assert state.json()["state_key"] == "eteinte"

    renamed = await client.patch(
        f"/api/projects/{project['id']}/elements/{element['id']}",
        json={"name": "Lampe art déco", "description": "Laiton brossé et verre opalin"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Lampe art déco"
    assert renamed.json()["reference_id"] == stable_reference


@pytest.mark.asyncio
async def test_existing_asset_seeds_only_the_anchor_view_as_approved(client, db_session):
    async with db_session() as session:
        project = Project(name="Legacy references")
        session.add(project)
        await session.flush()
        media = await create_media_item(
            session,
            file_path=Path("/references/legacy-chair.png"),
            materialize_asset=True,
        )
        project_id = project.id
        media_id = media.id

    created = await client.post(
        f"/api/projects/{project_id}/elements",
        json={"name": "Chaise", "element_type": "prop", "media_id": media_id},
    )
    assert created.status_code == 200, created.text
    pack = (await client.get(f"/api/projects/{project_id}/references")).json()["packs"][0]
    assert pack["views"][0]["view_key"] == "hero_3q"
    assert pack["views"][0]["status"] == "approved"
    assert pack["views"][0]["approved_media_id"] == media_id
    assert all(view["status"] == "missing" for view in pack["views"][1:])


@pytest.mark.asyncio
async def test_blocking_sync_is_idempotent_and_links_shots(client):
    project = (await client.post("/api/projects", json={"name": "Blocking references"})).json()
    await client.post(
        f"/api/projects/{project['id']}/elements",
        json={"name": "Salon", "element_type": "location"},
    )
    imported = await client.post(
        f"/api/projects/{project['id']}/direction/import",
        json={
            "script": """# SÉQUENCE 1 — Salon
| # | Durée | Code | Plan — texte intégral | Raccord entrant exact |
|---|---:|---|---|---|
| **01** | 4 s | **A** | Maya traverse le salon vers la fenêtre. | Début |
| **02** | 4 s | **B** | Maya continue dans le même axe. | Continuité |
""",
        },
    )
    assert imported.status_code == 200, imported.text

    first = await client.post(f"/api/projects/{project['id']}/references/sync-blocking")
    second = await client.post(f"/api/projects/{project['id']}/references/sync-blocking")
    assert first.status_code == 200, first.text
    assert first.json()["clusters"] >= 1
    assert first.json()["created"] >= 1
    assert second.json()["created"] == 0

    pack = (await client.get(f"/api/projects/{project['id']}/references")).json()["packs"][0]
    blocking_views = [view for view in pack["views"] if view["view_spec"].get("source") == "blocking-cluster-v1"]
    assert blocking_views
    assert blocking_views[0]["view_spec"]["used_by_shots"]

    production = (await client.get(f"/api/projects/{project['id']}/production")).json()
    linked = [
        shot["blocking"].get("location_reference")
        for sequence in production["sequences"]
        for shot in sequence["shots"]
    ]
    assert any(reference and reference["pack_id"] == pack["id"] for reference in linked)


@pytest.mark.asyncio
async def test_mnesis_location_prompts_are_automatic_and_split_visual_states(client, db_session):
    project = (await client.post("/api/projects", json={"name": "MNESIS"})).json()
    await client.post(
        f"/api/projects/{project['id']}/elements",
        json={"name": "Salon", "element_type": "location"},
    )
    imported = await client.post(
        f"/api/projects/{project['id']}/direction/import",
        json={
            "script": """# SÉQUENCE 1 — Salon
| # | Durée | Code | Plan — texte intégral | Raccord entrant exact |
|---|---:|---|---|---|
| **01** | 4 s | **A** | MNESIS. Medium Maya dans le salon près du judas. | Début |
| **02** | 4 s | **A** | Lumière blanche du matin. Medium Maya dans le salon. La pluie a cessé. | Ellipse |
""",
        },
    )
    assert imported.status_code == 200, imported.text
    synced = await client.post(f"/api/projects/{project['id']}/references/sync-blocking")
    assert synced.status_code == 200, synced.text

    pack = (await client.get(f"/api/projects/{project['id']}/references")).json()["packs"][0]
    blocking_views = [
        view for view in pack["views"]
        if view["view_spec"].get("source") == "blocking-cluster-v1"
    ]
    assert {view["view_spec"]["location_state"] for view in blocking_views} == {
        "APT_NIGHT_RAIN",
        "APT_MORNING",
    }
    assert all(
        view["view_spec"]["prompt_profile"] == "mnesis-location-v1"
        for view in blocking_views
    )

    morning = next(
        view for view in blocking_views
        if view["view_spec"]["location_state"] == "APT_MORNING"
    )
    async with db_session() as session:
        row = await session.get(ProjectReferenceView, morning["id"])
        prompt, media_ids, dimensions = await build_view_generation_request(
            session,
            project_id=project["id"],
            view=row,
        )
    assert "MNESIS LOCATION SKILL — AUTOMATIC AUGMENTATION" in prompt
    assert "APT_MORNING" in prompt
    assert "No extra hallway" in prompt
    assert media_ids == []
    assert dimensions == [1344, 768]


@pytest.mark.asyncio
async def test_composition_pins_revisions_and_orders_agy_references(db_session):
    async with db_session() as session:
        project = Project(name="Pinned composition")
        session.add(project)
        await session.flush()
        location_media = await create_media_item(
            session,
            file_path=Path("/references/clean-location.png"),
            width=1344,
            height=768,
            materialize_asset=True,
        )
        prop_media = await create_media_item(
            session,
            file_path=Path("/references/canonical-lamp.png"),
            width=768,
            height=768,
            materialize_asset=True,
        )
        location, _ = await create_project_element(
            session,
            project_id=project.id,
            name="Salon",
            element_type="location",
            media_id=location_media.id,
        )
        prop, _ = await create_project_element(
            session,
            project_id=project.id,
            name="Lampe",
            element_type="prop",
            media_id=prop_media.id,
        )
        location_pack = await ensure_reference_pack(session, location)
        prop_pack = await ensure_reference_pack(session, prop)
        await session.flush()
        location_view = await session.scalar(select(ProjectReferenceView).where(
            ProjectReferenceView.pack_id == location_pack.id,
            ProjectReferenceView.view_key == "master",
        ))
        prop_view = await session.scalar(select(ProjectReferenceView).where(
            ProjectReferenceView.pack_id == prop_pack.id,
            ProjectReferenceView.view_key == "hero_3q",
        ))
        composition = await create_composition(
            session,
            project_id=project.id,
            location_view_id=location_view.id,
            name="Salon avec lampe",
            prompt_delta="Lampe allumée, lumière chaude.",
            placement_guide_media_id=None,
            items=[{
                "project_element_id": prop.id,
                "reference_view_id": prop_view.id,
                "placement": {"x": 0.7, "y": 0.6, "scale": 0.18},
            }],
        )
        duplicate = await create_composition(
            session,
            project_id=project.id,
            location_view_id=location_view.id,
            name="Duplicate name does not fork identity",
            prompt_delta="Lampe allumée, lumière chaude.",
            placement_guide_media_id=None,
            items=[{
                "project_element_id": prop.id,
                "reference_view_id": prop_view.id,
                "placement": {"x": 0.7, "y": 0.6, "scale": 0.18},
            }],
        )
        assert duplicate.id == composition.id
        item = await session.scalar(select(ProjectCompositionItem).where(
            ProjectCompositionItem.composition_id == composition.id,
        ))
        assert item.source_revision_id == prop_view.approved_revision_id
        assert composition.base_location_revision_id == location_view.approved_revision_id

        prompt, media_ids, dimensions = await build_composition_generation_request(
            session,
            composition=composition,
        )
        assert media_ids == [location_media.id, prop_media.id]
        assert dimensions == [1344, 768]
        assert "<Picture 1> is the exact approved clean location plate" in prompt
        assert "<Picture 2> is the exact approved identity view" in prompt
        assert prompt.index("<Picture 1>") < prompt.index("<Picture 2>")


@pytest.mark.asyncio
async def test_deleting_element_soft_deletes_reference_graph(client, db_session):
    project = (await client.post("/api/projects", json={"name": "Reference trash"})).json()
    created = (await client.post(
        f"/api/projects/{project['id']}/elements",
        json={"name": "Telephone", "element_type": "prop"},
    )).json()
    await client.get(f"/api/projects/{project['id']}/references")
    deleted = await client.delete(f"/api/projects/{project['id']}/elements/{created['id']}")
    assert deleted.status_code == 200, deleted.text

    async with db_session() as session:
        element = await session.get(ProjectElement, created["id"])
        pack = await session.scalar(select(ProjectReferencePack).where(
            ProjectReferencePack.project_element_id == created["id"],
        ))
        views = list(await session.scalars(select(ProjectReferenceView).where(
            ProjectReferenceView.pack_id == pack.id,
        )))
        assert element.deleted_at is not None
        assert pack.deleted_at is not None
        assert views and all(view.deleted_at is not None for view in views)
