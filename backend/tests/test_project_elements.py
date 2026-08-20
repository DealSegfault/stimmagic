import json
from pathlib import Path

import pytest
from sqlalchemy import select

from agent.v2.tools.library import library
from database import Asset, Project, ProjectAsset, ProjectElement
from asset_service import restore_asset
from project_element_service import build_element_reference
from tests.helpers.media import create_media_item


def test_element_reference_normalizes_type_project_and_name():
    assert build_element_reference("location", "Maya", "Cuisine principale") == "loc_maya_cuisine_principale"
    assert build_element_reference("char", "Été Rouge", "Zoë") == "char_ete_rouge_zoe"
    assert build_element_reference("prop", "Maya", "Couteau") == "prop_maya_couteau"


@pytest.mark.asyncio
async def test_project_element_api_creates_lists_and_soft_deletes(client, db_session):
    async with db_session() as session:
        project = Project(name="Maya")
        session.add(project)
        await session.flush()
        media = await create_media_item(
            session,
            file_path=Path("/elements/maya-couteau.png"),
            file_format="png",
        )
        await session.commit()
        project_id = project.id
        media_id = media.id

    created = await client.post(
        f"/api/projects/{project_id}/elements",
        json={"name": "Couteau", "element_type": "prop", "media_id": media_id},
    )
    assert created.status_code == 200, created.text
    payload = created.json()
    assert payload["created"] is True
    assert payload["reference_id"] == "prop_maya_couteau"
    assert payload["media_id"] == media_id

    repeated = await client.post(
        f"/api/projects/{project_id}/elements",
        json={"name": "Couteau", "element_type": "prop", "media_id": media_id},
    )
    assert repeated.status_code == 200
    assert repeated.json()["created"] is False
    assert repeated.json()["id"] == payload["id"]

    listed = await client.get(f"/api/projects/{project_id}/elements")
    assert listed.status_code == 200
    assert [item["reference_id"] for item in listed.json()] == ["prop_maya_couteau"]

    async with db_session() as session:
        membership = await session.scalar(
            select(ProjectAsset).where(
                ProjectAsset.project_id == project_id,
                ProjectAsset.asset_id == payload["asset_id"],
                ProjectAsset.deleted_at.is_(None),
            )
        )
        assert membership is not None

    deleted = await client.delete(
        f"/api/projects/{project_id}/elements/{payload['id']}"
    )
    assert deleted.status_code == 200
    assert (await client.get(f"/api/projects/{project_id}/elements")).json() == []

    async with db_session() as session:
        row = await session.get(ProjectElement, payload["id"])
        assert row is not None and row.deleted_at is not None


@pytest.mark.asyncio
async def test_library_tool_creates_element_from_attached_media(db_session):
    async with db_session() as session:
        project = Project(name="Maya")
        session.add(project)
        await session.flush()
        media = await create_media_item(
            session,
            file_path=Path("/elements/maya-kitchen.png"),
            file_format="png",
        )
        await session.commit()

        result = json.loads(await library(
            action="element",
            operation="create",
            element_type="location",
            element_name="Kitchen",
            media_id=media.id,
            project_id=project.id,
            session=session,
        ))

        assert result["created"] is True
        assert result["reference_id"] == "loc_maya_kitchen"
        assert result["media_id"] == media.id

        listed = json.loads(await library(
            action="element",
            operation="list",
            project_id=project.id,
            session=session,
        ))
        assert listed["total"] == 1
        assert listed["items"][0]["reference_id"] == "loc_maya_kitchen"


@pytest.mark.asyncio
async def test_library_asset_trash_cascades_project_element(db_session):
    async with db_session() as session:
        project = Project(name="Maya")
        session.add(project)
        await session.flush()
        media = await create_media_item(
            session,
            file_path=Path("/elements/maya-tea-cup.png"),
            file_format="png",
        )
        element = json.loads(await library(
            action="element",
            operation="create",
            element_type="prop",
            element_name="Tasse",
            media_id=media.id,
            project_id=project.id,
            session=session,
        ))

        result = json.loads(await library(
            action="asset",
            operation="trash",
            media_id=media.id,
            project_id=project.id,
            session=session,
        ))

        assert result["status"] == "ok"
        assert result["items"][0]["deleted_element_ids"] == [element["id"]]
        asset = await session.scalar(select(Asset).where(Asset.id == element["asset_id"]))
        row = await session.get(ProjectElement, element["id"])
        assert asset is not None and asset.state == "trashed"
        assert row is not None and row.deleted_at is not None


@pytest.mark.asyncio
async def test_restoring_asset_restores_elements_tombstoned_by_trash(db_session):
    async with db_session() as session:
        project = Project(name="Restore symmetry")
        session.add(project)
        await session.flush()
        media = await create_media_item(session, file_path=Path("/elements/restore.png"), file_format="png")
        element = json.loads(await library(
            action="element", operation="create", element_type="prop",
            element_name="Restore prop", media_id=media.id,
            project_id=project.id, session=session,
        ))
        await library(action="asset", operation="trash", media_id=media.id, project_id=project.id, session=session)
        asset = await session.scalar(select(Asset).where(Asset.id == element["asset_id"]))
        await restore_asset(session, asset_id=asset.id)
        restored = await session.get(ProjectElement, element["id"])
        assert restored is not None and restored.deleted_at is None


@pytest.mark.asyncio
async def test_library_tool_prefers_valid_media_when_asset_id_is_stale(db_session):
    async with db_session() as session:
        project = Project(name="Maya")
        session.add(project)
        await session.flush()
        media = await create_media_item(
            session,
            file_path=Path("/elements/maya-close-view.png"),
            file_format="png",
        )
        await session.commit()

        result = json.loads(await library(
            action="element",
            operation="create",
            element_type="location",
            element_name="Kitchen close view",
            asset_id=999999,
            media_id=media.id,
            project_id=project.id,
            session=session,
        ))

        assert result["created"] is True
        assert result["media_id"] == media.id


@pytest.mark.asyncio
async def test_library_tool_creates_element_from_path(tmp_path, db_session):
    test_img = tmp_path / "workspace_element.png"
    # Create minimal 1x1 png file
    import io
    from PIL import Image
    im = Image.new("RGBA", (10, 10), (255, 0, 0, 255))
    im.save(test_img)

    async with db_session() as session:
        project = Project(name="Maya")
        session.add(project)
        await session.flush()

        result = json.loads(await library(
            action="element",
            operation="create",
            element_type="location",
            element_name="Kitchen close view",
            path=str(test_img),
            project_id=project.id,
            session=session,
        ))

        assert result["created"] is True
        assert result["reference_id"] == "loc_maya_kitchen_close_view"
        assert result["media_id"] is not None
