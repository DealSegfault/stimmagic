import json

from agent.v2.service import _claim_generation_call, _generation_call_key, _is_generation_run_code


def test_detects_catalog_generation_run_code():
    args = json.dumps({
        "code": (
            "from stimma.tools.reference_to_video import minimax_h3_r2v_turbo\n"
            "r = await minimax_h3_r2v_turbo(prompt='room', input_images=[1])"
        )
    })

    assert _is_generation_run_code("run_code", args) is True


def test_allows_post_generation_ffmpeg_run_code():
    args = json.dumps({
        "code": "await stimma.ffmpeg('-i', 'a.mp4', 'joined.mp4')"
    })

    assert _is_generation_run_code("run_code", args) is False
    assert _is_generation_run_code("view_image", args) is False


def test_claims_equivalent_generation_only_once_per_batch():
    args = json.dumps({
        "code": "from stimma.tools.reference_to_video import minimax_h3_r2v_turbo\n"
        "r = await minimax_h3_r2v_turbo(prompt='room', input_images=[1])"
    })
    claimed = set()

    assert _generation_call_key("run_code", args)
    assert _claim_generation_call("run_code", args, claimed) is None
    assert "Skipped duplicate generation request" in (
        _claim_generation_call("run_code", args, claimed) or ""
    )


def test_non_generation_calls_are_not_claimed():
    claimed = set()

    assert _claim_generation_call(
        "run_code", json.dumps({"code": "print('hello')"}), claimed
    ) is None
    assert claimed == set()
