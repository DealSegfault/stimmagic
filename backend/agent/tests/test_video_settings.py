"""Tests for chat-level MiniMax H3 video preferences."""

from agent.v2.video_settings import (
    apply_video_chat_preferences,
    normalize_video_chat_settings,
    resolve_video_dimensions,
)


def test_normalize_video_settings_bounds_and_fast_mode():
    assert normalize_video_chat_settings({
        "video_quick_mode": True,
        "video_steps": 99,
        "video_resolution": "2K",
        "video_duration": 20,
    }) == {
        "fast": True,
        "steps": 50,
        "resolution": "2k",
        "duration": 15.0,
    }


def test_fast_mode_forces_eight_steps_and_resolution_uses_supported_pair():
    params = {"steps": 20, "duration": 4, "width": 1344, "height": 768}
    width, height, settings = apply_video_chat_preferences(
        params,
        1344,
        768,
        {"steps": {}, "duration": {}, "width": {}, "height": {}},
        {
            "video_quick_mode": True,
            "video_steps": 30,
            "video_resolution": "480",
            "video_duration": 6,
        },
        [(1344, 768), (960, 544), (864, 480)],
    )

    assert (width, height) == (864, 480)
    assert params["steps"] == 8
    assert params["duration"] == 6.0
    assert settings["fast"] is True

    standard_params = {"steps": 8, "duration": 4}
    apply_video_chat_preferences(
        standard_params,
        1344,
        768,
        {"steps": {}, "duration": {}},
        {
            "video_quick_mode": False,
            "video_steps": 30,
            "video_duration": 5,
        },
    )
    assert standard_params["steps"] == 30


def test_unconstrained_resolution_preserves_aspect_ratio():
    assert resolve_video_dimensions(1920, 1080, "720") == (1248, 704)
