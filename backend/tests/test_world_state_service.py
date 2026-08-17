import json
from pathlib import Path
import pytest
from sqlalchemy import select

from agent.v2.tools.world_state import get_world_state, update_world_state
from database import Project, ProjectDirection, ProjectElement, ProjectScene
from tests.helpers.media import create_media_item
from world_state_service import (
    build_project_world_state,
    detect_missing_references,
    distill_h3_shot_context,
    update_entity_state,
)


@pytest.mark.asyncio
async def test_world_state_build_and_detect_missing(db_session):
    async with db_session() as session:
        project = Project(name="Maya")
        session.add(project)
        await session.flush()

        # Add project direction
        direction = ProjectDirection(
            project_id=project.id,
            script_name="Maya Episode 1",
            summary="Maya in Paris",
            context=json.dumps({"palette": "moody"}),
        )
        session.add(direction)

        # Add a character element WITH an asset
        media_maya = await create_media_item(
            session,
            file_path=Path("/elements/maya.png"),
            file_format="png",
        )
        await session.flush()

        from project_element_service import create_project_element
        elem_maya, _ = await create_project_element(
            session,
            project_id=project.id,
            name="Maya",
            element_type="character",
            media_id=media_maya.id,
            description="Young woman with wavy dark hair",
        )

        # Add a location element WITHOUT an asset (empty or not created yet)
        elem_cafe = ProjectElement(
            project_id=project.id,
            name="Café Parisien",
            element_type="location",
            reference_id="loc_maya_cafe_parisien",
            description="Retro Parisian bistro",
            asset_id=None,
        )
        session.add(elem_cafe)

        # Add a scene
        scene1 = ProjectScene(
            project_id=project.id,
            sequence_number=1,
            scene_number=1,
            title="Intro",
            description="Maya enters the café under the rain",
            context=json.dumps({"continuity": {"maya_pose": "standing by door"}}),
        )
        session.add(scene1)
        await session.commit()

        project_id = project.id
        scene_id = scene1.id

    # Test building world state
    async with db_session() as session:
        world_state = await build_project_world_state(session, project_id=project_id, scene_id=scene_id)
        assert world_state["project_id"] == project_id
        assert world_state["project_name"] == "Maya"
        assert "char_maya_maya" in world_state["entities"]["characters"]
        assert "loc_maya_cafe_parisien" in world_state["entities"]["locations"]
        assert world_state["continuity_buffer"] == {}

        # Test detecting missing references for a shot prompt
        missing = detect_missing_references(world_state, "Maya drinks coffee at the café")
        assert len(missing) == 1
        assert missing[0]["reference_id"] == "loc_maya_cafe_parisien"
        assert missing[0]["element_type"] == "location"

        # Test distilling H3 shot context with character and prop
        from project_element_service import create_project_element as create_elem
        media_window = await create_media_item(
            session,
            file_path=Path("/elements/window.png"),
            file_format="png",
        )
        await session.flush()
        elem_window, _ = await create_elem(
            session,
            project_id=project_id,
            name="fenetre",
            element_type="prop",
            media_id=media_window.id,
            description="Maya's rain-covered window",
        )
        await session.commit()

    async with db_session() as session:
        world_state = await build_project_world_state(session, project_id=project_id, scene_id=scene_id)
        prompt, manifest = distill_h3_shot_context(
            world_state,
            "@prop_maya_fenetre Maya looks through the window",
        )
        assert "integrated_multimodal_description:" in prompt
        assert "<Picture 1>" in prompt
        assert "<Picture 2>" in prompt
        assert len(manifest) == 2
        labels = [m["label"] for m in manifest]
        assert "Picture 1" in labels
        assert "Picture 2" in labels
        assert any(m["element_type"] == "prop" for m in manifest)


@pytest.mark.asyncio
async def test_world_state_agent_tools(db_session):
    async with db_session() as session:
        project = Project(name="Maya Proj")
        session.add(project)
        await session.flush()
        project_id = project.id

        from project_element_service import create_project_element
        media = await create_media_item(
            session,
            file_path=Path("/elements/maya-portrait.png"),
            file_format="png",
        )
        await session.flush()
        await create_project_element(
            session,
            project_id=project_id,
            name="Maya",
            element_type="character",
            media_id=media.id,
            description="Wool sweater",
        )
        await session.commit()

    async with db_session() as session:
        state_result = await get_world_state(
            shot_prompt="Maya looks at window",
            session=session,
            project_id=project_id,
        )
        assert "entities" in state_result
        assert "char_maya_proj_maya" in state_result["entities"]["characters"]
        assert state_result["has_missing_references"] is False

        # Update entity state via tool
        update_result = await update_world_state(
            reference_id="char_maya_proj_maya",
            description="Wearing leather jacket",
            session=session,
            project_id=project_id,
        )
        assert update_result["updated"] is True
        assert update_result["description"] == "Wearing leather jacket"
