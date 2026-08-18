from shot_continuity_service import (
    build_shot_generation_contract,
    parse_shot_duration,
    validate_generation_request,
)


def _contract():
    return build_shot_generation_contract(
        project_id=1,
        scene={"id": 7, "sequence_number": 1, "scene_number": 1, "context": {}},
        shot_context={
            "shot_number": 4,
            "current": {"duration": "4 s", "description": "Maya lowers the tea bag"},
            "previous": {"shot_number": 3},
        },
        reference_manifest=[
            {"media_id": 900, "role": "continuity_anchor"},
            {"media_id": 120, "role": "location_canonical"},
            {"media_id": 49, "role": "character"},
        ],
        previous_acceptance={"media_id": 152, "last_frame_media_id": 900},
    )


def _compose_contract():
    contract = _contract()
    contract["workflow"] = "compose_opening_keyframe_then_i2v"
    return contract


def test_parse_shot_duration_supports_script_cells():
    assert parse_shot_duration("4 s") == 4
    assert parse_shot_duration("5 secondes") == 5


def test_contract_blocks_stale_reference_and_wrong_output_settings():
    errors = validate_generation_request(
        _contract(),
        task_type="image-to-video",
        final_params={"duration": 5, "width": 1216, "height": 704},
        input_media_ids=[150, 146, 120, 49],
    )
    assert any("duration mismatch" in error for error in errors)
    assert any("dimensions mismatch" in error for error in errors)
    assert any("wrong continuity anchor" in error for error in errors)
    assert any("outside the resolved shot manifest" in error for error in errors)


def test_contract_accepts_exact_ordered_manifest():
    errors = validate_generation_request(
        _contract(),
        task_type="image-to-video",
        final_params={"duration": 4, "width": 1344, "height": 768},
        input_media_ids=[900, 120, 49],
    )
    assert errors == []


def test_insert_return_requires_keyframe_then_i2v():
    contract = _compose_contract()
    direct_r2v_errors = validate_generation_request(
        contract,
        task_type="reference-to-video",
        final_params={"duration": 4, "width": 1344, "height": 768},
        input_media_ids=[900, 120, 49],
    )
    assert any("composed opening keyframe" in error for error in direct_r2v_errors)

    keyframe_errors = validate_generation_request(
        contract,
        task_type="image-to-image",
        final_params={},
        input_media_ids=[900, 120, 49],
    )
    assert keyframe_errors == []

    i2v_errors = validate_generation_request(
        contract,
        task_type="image-to-video",
        final_params={"duration": 4, "width": 1344, "height": 768},
        input_media_ids=[901],
        session_media_ids=[901],
    )
    assert i2v_errors == []
