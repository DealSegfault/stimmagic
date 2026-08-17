import json

from agent.v2.service import _is_generation_run_code


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
