import json

from world_state_service import (
    build_script_shot_context,
    compact_world_state_for_agent,
    extract_script_shots,
    infer_shot_number,
)


def test_script_shot_context_separates_scene_and_plan_numbers():
    script = """| # | Durée | Code | Plan — texte intégral | Raccord entrant exact |
|---|---:|---|---|---|
| **03** | 4 s | **A** | Insert bouilloire : eau chaude versée. | Insert objet. |
| **04** | 4 s | **A** | Maya descend le sachet puis attend. | Retour personnage après insert. |
"""
    shots = extract_script_shots(script)
    assert [shot["shot_number"] for shot in shots] == [3, 4]
    assert infer_shot_number("Génère le plan 04") == 4
    context = build_script_shot_context(
        {"scene_number": 1, "title": "LE CALME", "description": script},
        4,
    )
    assert context["current"]["shot_number"] == 4
    assert context["previous"]["shot_number"] == 3
    assert context["scene_number"] == 1


def test_compact_world_state_keeps_ids_and_bounds_scene_context():
    state = {
        "project_id": 1,
        "project_name": "Maya",
        "entities": {
            "props": {
                "prop_maya_kettle": {
                    "id": 1,
                    "asset_id": 2,
                    "revision_id": 3,
                    "media_id": 4,
                    "element_type": "prop",
                    "name": "bouilloire",
                    "reference_id": "prop_maya_kettle",
                    "description": "canonical kettle",
                    "updated_at": "bookkeeping",
                },
            },
        },
        "scenes": [
            {
                "id": 1,
                "sequence_number": 1,
                "scene_number": 3,
                "title": "Kitchen",
                "description": "A kitchen",
                "context": {"huge": "x" * 100_000},
            },
        ],
        "current_scene": {
            "id": 1,
            "sequence_number": 1,
            "scene_number": 3,
            "title": "Kitchen",
            "description": "A kitchen",
            "prompt": "x" * 100_000,
            "context": {"continuity": "y" * 100_000},
            "dependencies": [],
            "blockers": [],
        },
        "reference_assets": [],
        "global_context": {},
        "continuity_buffer": {},
    }

    compact = compact_world_state_for_agent(state)
    assert compact["entities"]["props"]["prop_maya_kettle"]["media_id"] == 4
    assert "updated_at" not in compact["entities"]["props"]["prop_maya_kettle"]
    assert len(json.dumps(compact["scenes"][0])) < 1_500
    assert len(compact["current_scene"]["prompt"]) < 6_000
    assert len(compact["current_scene"]["context"]["continuity"]) < 4_000
