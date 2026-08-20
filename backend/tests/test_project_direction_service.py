import json

import pytest
from sqlalchemy import select

from database import Board, Chat, Project, ProjectScene
from project_direction_service import extract_script_directives, parse_script, reconcile_script, record_event


def test_parse_repeated_shot_tables_as_separate_scenes():
    script = """# Shot map

| # | Durée | Code | Plan — texte intégral | Raccord entrant exact |
|---|---:|---|---|---|
| **01** | 4 s | **A** | Plan d'ouverture. | Début |

---

| # | Durée | Code | Plan — texte intégral | Raccord entrant exact |
|---|---:|---|---|---|
| **02** | 6 s | **A** | Maya entre. | Cut |

---

| # | Durée | Code | Plan — texte intégral | Raccord entrant exact |
|---|---:|---|---|---|
| **03** | 5 s | **B** | Maya se retourne. | Réaction |
"""

    scenes = parse_script(script)

    assert len(scenes) == 3
    assert [scene["sequence_number"] for scene in scenes] == [1, 2, 3]
    assert [scene["title"] for scene in scenes] == ["Scene 1", "Scene 2", "Scene 3"]
    assert "**01**" in scenes[0]["description"]
    assert "**02**" in scenes[1]["description"]
    assert "**03**" in scenes[2]["description"]


def test_parse_sequence_headings_as_scenes_when_no_scene_headings_exist():
    script = """# Script

## SÉQUENCE 1 — L'installation
Maya prépare un thé.

## SÉQUENCE 2 — La révélation
Le téléphone sonne.
"""

    scenes = parse_script(script)

    assert len(scenes) == 2
    assert scenes[0]["sequence_number"] == 1
    assert scenes[0]["title"] == "L'installation"
    assert scenes[0]["description"].endswith("Maya prépare un thé.")
    assert scenes[1]["sequence_number"] == 2
    assert scenes[1]["title"] == "La révélation"
    assert scenes[1]["description"] == "Le téléphone sonne."


def test_parse_sequence_shot_table_into_canonical_plans():
    script = """# SÉQUENCE 1 — Cuisine
| # | Durée | Code | Plan — texte intégral | Raccord entrant exact |
|---|---:|---|---|---|
| **01** | 4 s | **A** | Maya verse le thé. | Début |
| **02** | 6 s | **C** | Maya regarde la porte. | Raccord exact |
"""

    scenes = parse_script(script)

    assert len(scenes) == 1
    assert [shot["shot_number"] for shot in scenes[0]["shots"]] == [1, 2]
    assert scenes[0]["shots"][0]["transition_policy"] == "independent"
    assert scenes[0]["shots"][1]["transition_policy"] == "continuity"
    assert scenes[0]["shots"][1]["incoming_cut"] == "Raccord exact"
    assert scenes[0]["scene_description"] == ""


def test_shot_map_keeps_optional_scene_notes_without_copying_the_table():
    script = """# SÉQUENCE 1 — Cuisine
Ambiance chaude, appartement calme.

| # | Durée | Code | Plan — texte intégral | Raccord entrant exact |
|---|---:|---|---|---|
| **01** | 4 s | **A** | Maya verse le thé. | Début |
"""

    scenes = parse_script(script)

    assert scenes[0]["scene_description"] == "Ambiance chaude, appartement calme."
    assert "| **01** |" in scenes[0]["description"]


def test_script_preamble_is_directive_not_sequence_content():
    script = """# FILM — production-safe
## LÉGENDE GÉNÉRATION
- A = génération indépendante.
- B = même moment, angle différent.

# SÉQUENCE 1 — Le calme
| # | Durée | Code | Plan — texte intégral | Raccord entrant exact |
|---|---:|---|---|---|
| **01** | 4 s | **A** | Maya regarde la fenêtre. | Début |
"""

    scenes = parse_script(script)

    assert extract_script_directives(script).startswith("# FILM")
    assert "LÉGENDE GÉNÉRATION" not in scenes[0]["description"]
    assert scenes[0]["shots"][0]["description"] == "Maya regarde la fenêtre."


def test_explicit_scene_headings_still_take_precedence():
    script = """SÉQUENCE 1 — Nuit
SCÈNE 1 — Cuisine
Maya verse le thé.
SCÈNE 2 — Porte
Quelqu'un frappe.
"""

    scenes = parse_script(script)

    assert len(scenes) == 2
    assert [scene["sequence_number"] for scene in scenes] == [1, 1]
    assert [scene["title"] for scene in scenes] == ["Cuisine", "Porte"]


@pytest.mark.asyncio
async def test_reconcile_preserves_matching_boards_and_removes_stale_scenes(db_session):
    async with db_session() as session:
        project = Project(name="Direction cascade test")
        session.add(project)
        await session.flush()

        first_payload, first_change = await reconcile_script(
            session,
            project.id,
            "SCÈNE 1 — Cuisine\nMaya verse le thé.\nSCÈNE 2 — Porte\nQuelqu'un frappe.",
            "Test",
            None,
            {},
        )
        await session.commit()
        first_scene = first_payload["scenes"][0]
        stale_scene = first_payload["scenes"][1]
        assert first_change["created_scene_ids"]

        approved_scene = await session.get(ProjectScene, first_scene["id"])
        approved_scene.status = "complete"
        approved_scene.validation_status = "approved"
        stale_chat = Chat(
            name="Scene chat",
            project_id=project.id,
            additional_instructions="DIRECTION_CONTEXT=" + json.dumps({"scene_id": stale_scene["id"]}),
        )
        session.add(stale_chat)
        await session.flush()
        await record_event(
            session,
            project.id,
            "scene_chat_created",
            scene_id=stale_scene["id"],
            chat_id=stale_chat.id,
        )
        await session.commit()

        second_payload, second_change = await reconcile_script(
            session,
            project.id,
            "SCÈNE 1 — Cuisine\nMaya ouvre la porte.\nSCÈNE 3 — Rue\nLa ville s'éveille.",
            "Test",
            None,
            {},
        )
        await session.commit()

        assert second_payload["scenes"][0]["id"] == first_scene["id"]
        assert second_payload["scenes"][0]["board_id"] == first_scene["board_id"]
        assert second_payload["scenes"][0]["description"] == "Maya ouvre la porte."
        assert stale_scene["id"] in second_change["removed_scene_ids"]
        assert len(second_change["created_scene_ids"]) == 1
        assert second_payload["scenes"][0]["validation_status"] == "pending"
        assert second_payload["scenes"][0]["status"] == "planned"

        stale_board = await session.get(Board, stale_scene["board_id"])
        assert stale_board is not None and stale_board.deleted_at is not None
        await session.refresh(stale_chat)
        assert json.loads(stale_chat.additional_instructions.split("DIRECTION_CONTEXT=", 1)[1])["script_removed"] is True
        live_scenes = (await session.execute(
            select(ProjectScene).where(ProjectScene.project_id == project.id)
        )).scalars().all()
        assert {scene.title for scene in live_scenes} == {"Cuisine", "Rue"}
