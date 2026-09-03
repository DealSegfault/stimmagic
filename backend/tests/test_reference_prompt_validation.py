from reference_prompt_validation import (
    format_reference_prompt_warning,
    reference_prompt_mismatches,
)


def test_phantom_video_reference_is_reported():
    mismatches = reference_prompt_mismatches(
        "integrated_multimodal_description: <Video 1> supplies the movement",
        {"input_images": ["robot.png"], "input_videos": []},
    )

    assert len(mismatches) == 1
    assert mismatches[0]["type"] == "unknown_prompt_reference"
    assert "aucune référence vidéo" in mismatches[0]["reason"]


def test_ref2va_accepts_explicit_paired_video_audio_tags():
    mismatches = reference_prompt_mismatches(
        (
            "integrated_multimodal_description: <Picture 1> identity; "
            "<Audio 1> soundtrack; <Video 1> motion"
        ),
        {
            "input_images": ["robot.png"],
            "input_videos": ["motion.mp4"],
            # The video's embedded soundtrack is paired automatically.
            "input_audios": [],
        },
    )

    assert mismatches == []


def test_ref2va_allows_attached_media_without_prompt_tags():
    mismatches = reference_prompt_mismatches(
        (
            "subject_definitions: <Picture 1> identity\n"
            "summary: Use the attached still image only."
        ),
        {
            "input_images": ["robot.png"],
            "input_videos": ["motion.mp4"],
            "input_audios": ["score.wav"],
        },
    )

    assert mismatches == []


def test_ref2va_allows_video_without_implicit_audio_tag():
    mismatches = reference_prompt_mismatches(
        "<Picture 1> identity; <Video 1> motion",
        {"input_images": ["robot.png"], "input_videos": ["motion.mp4"]},
    )

    assert mismatches == []


def test_ref2va_reports_only_an_explicit_unknown_tag():
    mismatches = reference_prompt_mismatches(
        "<Picture 1> identity; <Video 2> motion",
        {"input_images": ["robot.png"], "input_videos": ["motion.mp4"]},
    )

    assert len(mismatches) == 1
    assert mismatches[0]["type"] == "unknown_prompt_reference"
    assert "<Video 2>" in mismatches[0]["reason"]


def test_warning_is_ready_for_confirmation_dialog():
    warning = format_reference_prompt_warning(
        [
            {
                "reason": "le prompt mentionne <Video 1>, mais aucune référence vidéo n'est attachée"
            }
        ]
    )

    assert warning.startswith("Attention :")
    assert "Êtes-vous sûr de vouloir démarrer la génération ?" in warning
