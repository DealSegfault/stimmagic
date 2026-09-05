from types import SimpleNamespace

from runtime_mode import ingestion_required, is_lean_mode, is_stimma_cloud_enabled, local_vision_enabled


def test_lean_mode_disables_cloud_and_local_vision(monkeypatch):
    monkeypatch.setenv("STIMMA_LEAN_MODE", "1")

    assert is_lean_mode() is True
    assert is_stimma_cloud_enabled() is False
    assert local_vision_enabled() is False


def test_runtime_mode_can_be_opted_out(monkeypatch):
    monkeypatch.setenv("STIMMA_LEAN_MODE", "0")

    assert is_lean_mode() is False
    assert is_stimma_cloud_enabled() is True
    assert local_vision_enabled() is True


def test_ingestion_is_unneeded_without_folders_or_background_phases():
    settings = SimpleNamespace(
        profiles=[SimpleNamespace(folders=[])],
        clip=SimpleNamespace(enabled=False),
        face_detection=SimpleNamespace(enabled=False),
        captioning=SimpleNamespace(enabled=False),
    )

    assert ingestion_required(settings) is False


def test_ingestion_is_required_for_watched_folder_or_enabled_phase():
    phase_disabled = SimpleNamespace(
        profiles=[SimpleNamespace(folders=[])],
        clip=SimpleNamespace(enabled=False),
        face_detection=SimpleNamespace(enabled=False),
        captioning=SimpleNamespace(enabled=False),
    )
    watched = SimpleNamespace(path="/tmp/assets")
    phase_enabled = SimpleNamespace(
        profiles=[SimpleNamespace(folders=[watched])],
        clip=SimpleNamespace(enabled=False),
        face_detection=SimpleNamespace(enabled=False),
        captioning=SimpleNamespace(enabled=False),
    )
    clip_enabled = SimpleNamespace(
        profiles=[SimpleNamespace(folders=[])],
        clip=SimpleNamespace(enabled=True),
        face_detection=SimpleNamespace(enabled=False),
        captioning=SimpleNamespace(enabled=False),
    )

    assert ingestion_required(phase_disabled) is False
    assert ingestion_required(phase_enabled) is True
    assert ingestion_required(clip_enabled) is True
