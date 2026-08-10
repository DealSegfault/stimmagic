"""Defaults for opt-in live generation previews."""

from config import Settings


def test_generation_previews_default_off():
    assert Settings.model_fields["show_image_generation_previews"].default is False
    assert Settings.model_fields["show_video_generation_previews"].default is False
