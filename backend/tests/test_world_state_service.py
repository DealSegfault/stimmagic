import json
from pathlib import Path
import pytest
from sqlalchemy import select

from agent.v2.tools.world_state import get_world_state, update_world_state
from database import (
    Asset,
    AssetRevision,
    Board,
    BoardAssetItem,
    BoardSection,
    Project,
    ProjectDirection,
    ProjectElement,
    ProjectScene,
    ProjectShot,
)
from tests.helpers.media import create_media_item
from world_state_service import (
    build_shot_reference_manifest,
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


@pytest.mark.asyncio
async def test_world_state_resolves_scene_coordinates_and_board_references(db_session):
    async with db_session() as session:
        project = Project(name="Sequence Project")
        session.add(project)
        await session.flush()

        board = Board(name="S01 · Scene 3", project_id=project.id)
        session.add(board)
        await session.flush()
        references = BoardSection(
            board_id=board.id,
            name="References",
            is_default=True,
            display_order=0,
        )
        session.add(references)

        media = await create_media_item(
            session,
            file_path=Path("/references/maya.png"),
            file_format="png",
        )
        await session.flush()
        asset = Asset(asset_type="image", title="Maya reference")
        session.add(asset)
        await session.flush()
        revision = AssetRevision(
            asset_id=asset.id,
            primary_media_id=media.id,
            revision_number=1,
        )
        session.add(revision)
        await session.flush()
        asset.current_revision_id = revision.id
        session.add(
            ProjectScene(
                project_id=project.id,
                board_id=board.id,
                sequence_number=1,
                scene_number=3,
                title="La cuisine",
                description="Maya entre dans la cuisine.",
                context=json.dumps({"time": "night"}),
            )
        )
        session.add(
            BoardAssetItem(
                board_section_id=references.id,
                asset_id=asset.id,
                display_order=0,
            )
        )
        await session.commit()
        project_id = project.id

    async with db_session() as session:
        state = await get_world_state(
            sequence_number=1,
            scene_number=3,
            session=session,
            project_id=project_id,
        )

        assert state["current_scene"]["title"] == "La cuisine"
        assert state["current_scene"]["context"] == {"time": "night"}
        assert state["current_scene"]["board_id"] == board.id
        assert state["reference_assets"][0]["title"] == "Maya reference"
        assert state["reference_assets"][0]["media_id"] == media.id


def test_project_context_read_tools_are_available_to_agent_chats():
    from agent.v2.tools_registry import get_tools_schema

    names = {item["function"]["name"] for item in get_tools_schema("agent")}
    assert "get_world_state" in names
    assert "get_project_direction" in names


def test_project_context_read_tools_can_be_hidden_for_standalone_chats():
    from agent.v2.tools_registry import get_tools_schema

    names = {
        item["function"]["name"]
        for item in get_tools_schema(
            "agent",
            exclude_names={
                "get_world_state",
                "get_project_direction",
                "list_shot_generations",
                "accept_shot_generation",
            },
        )
    }
    assert "get_world_state" not in names
    assert "get_project_direction" not in names
    assert "list_shot_generations" not in names
    assert "accept_shot_generation" not in names


def test_shot_reference_manifest_does_not_match_generic_project_tokens():
    state = {
        "current_scene": {"title": "LE CALME"},
        "entities": {
            "characters": {
                "char_maya": {
                    "media_id": 1,
                    "reference_id": "char_maya",
                    "name": "mayaalvarez",
                    "description": "Maya",
                },
            },
            "locations": {
                "loc_appartement": {
                    "media_id": 2,
                    "reference_id": "loc_appartement",
                    "name": "appartement",
                    "description": "Open kitchen and living room",
                },
            },
            "props": {
                "prop_tea": {
                    "media_id": 3,
                    "reference_id": "prop_tea",
                    "name": "sachet_the_maya_viewsheet",
                    "description": "Canonical tea bag viewsheet",
                },
                "prop_kettle": {
                    "media_id": 4,
                    "reference_id": "prop_kettle",
                    "name": "bouilloire_maya_viewsheet",
                    "description": "Kettle from the previous plan",
                },
                "prop_last_frame": {
                    "media_id": 5,
                    "reference_id": "prop_maya_last_frame_plan_3",
                    "name": "last_frame_plan_3",
                    "description": "Accepted frame from the previous plan",
                },
            },
        },
    }
    shot_context = {
        "current": {
            "description": "Maya lowers the tea bag into the mug and waits.",
            "incoming_cut": "Independent return to character.",
            "transition_policy": "independent",
        },
    }

    manifest = build_shot_reference_manifest(state, shot_context)

    assert [item["reference_id"] for item in manifest] == [
        "char_maya",
        "loc_appartement",
        "prop_tea",
    ]


@pytest.mark.asyncio
async def test_world_state_resolves_global_plan_and_neighbors_without_scene_mixup(db_session):
    async with db_session() as session:
        project = Project(name="Global shot lookup")
        session.add(project)
        await session.flush()
        first = ProjectScene(
            project_id=project.id,
            sequence_number=1,
            scene_number=1,
            title="Le calme",
            description="La séquence calme.",
        )
        second = ProjectScene(
            project_id=project.id,
            sequence_number=2,
            scene_number=2,
            title="La porte",
            description="La séquence de la porte.",
        )
        session.add_all([first, second])
        await session.flush()
        session.add_all([
            ProjectShot(
                project_id=project.id,
                scene_id=first.id,
                shot_number=1,
                source_key="sequence:1::shot:1",
                title="Plan 01 · pluie",
                description="Pluie contre les fenêtres.",
                prompt="Pluie contre les fenêtres.",
                transition_policy="independent",
            ),
            ProjectShot(
                project_id=project.id,
                scene_id=second.id,
                shot_number=2,
                source_key="sequence:2::shot:2",
                title="Plan 02 · porte",
                description="Maya regarde la porte.",
                prompt="Maya regarde la porte.",
                transition_policy="independent",
            ),
        ])
        await session.commit()
        project_id = project.id

    async with db_session() as session:
        state = await get_world_state(
            shot_number=2,
            shot_prompt="Génère le plan 02",
            session=session,
            project_id=project_id,
        )

    assert state["current_scene"]["title"] == "La porte"
    assert state["shot_context"]["current"]["title"] == "Plan 02 · porte"
    assert state["shot_context"]["previous"]["title"] == "Plan 01 · pluie"
    assert state["generation_contract"]["shot_id"] == state["shot_context"]["current"]["id"]
