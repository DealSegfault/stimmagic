"""Configuration contraction for external Sources and managed staging."""

import app_dirs
import pytest
import yaml
from sqlalchemy import func, select

from config import Settings, ensure_config_exists, reload_settings
from config_writer import remove_profile_section
from background_work_filters import media_eligible_for_background_work
from database import MediaItem
from storage_service import register_external_asset
from tests.helpers.media import create_media_item, generate_test_image


def test_legacy_destination_roles_become_hidden_migration_roots(tmp_path, monkeypatch):
    legacy_root = tmp_path / "old-output"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
profiles:
  - id: default
    name: Default
    folders:
      - path: {legacy_root}
        readonly: false
        allow_generate: true
        is_uploads_folder: true
        uploads_subfolder: uploads
    markers: []
llms: {{}}
clip:
  model: ViT-g-14
  pretrained: laion2b_s12b_b42k
face_detection:
  enabled: false
server:
  host: 127.0.0.1
  port: 8000
"""
    )

    settings = Settings.load_config(str(config_path))
    profile = settings.get_profile("default")

    assert profile is not None
    assert profile.legacy_managed_roots == [str(legacy_root)]
    assert profile.folders[0].path == str(legacy_root)
    assert "readonly" not in profile.folders[0].model_dump()
    assert "allow_generate" not in profile.folders[0].model_dump()
    assert "is_uploads_folder" not in profile.folders[0].model_dump()
    assert "uploads_subfolder" not in profile.folders[0].model_dump()

    persisted = yaml.safe_load(config_path.read_text())
    persisted_profile = persisted["profiles"][0]
    assert persisted_profile["legacy_managed_roots"] == [str(legacy_root)]
    assert persisted_profile["folders"] == [{"path": str(legacy_root)}]

    monkeypatch.setattr(app_dirs, "get_config_path", lambda: config_path)
    assert remove_profile_section("default", "legacy_managed_roots") is True
    persisted = yaml.safe_load(config_path.read_text())
    assert "legacy_managed_roots" not in persisted["profiles"][0]


def test_new_style_profile_needs_no_sources(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
profiles:
  - id: default
    name: Default
    folders: []
    markers: []
llms: {}
clip:
  model: ViT-g-14
  pretrained: laion2b_s12b_b42k
face_detection:
  enabled: false
server:
  host: 127.0.0.1
  port: 8000
"""
    )

    profile = Settings.load_config(str(config_path)).get_profile("default")

    assert profile is not None
    assert profile.folders == []
    assert profile.legacy_managed_roots == []


def test_fresh_install_config_starts_without_sources(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    cache_dir = tmp_path / "cache"
    config_path = data_dir / "config.yaml"

    monkeypatch.setattr(app_dirs, "get_data_dir", lambda: data_dir)
    monkeypatch.setattr(app_dirs, "get_cache_dir", lambda: cache_dir)
    monkeypatch.setattr(app_dirs, "get_config_path", lambda: config_path)
    monkeypatch.setattr(
        app_dirs,
        "get_profile_dir",
        lambda profile_id=None: data_dir / "profiles" / (profile_id or "default"),
    )

    created_path = ensure_config_exists()
    profile = Settings.load_config(str(created_path)).profiles[0]

    assert created_path == config_path
    assert profile.folders == []
    assert not (tmp_path / "Documents" / "Stimma").exists()


async def test_settings_exposes_only_external_source_fields(client, tmp_path):
    before = await client.get("/api/settings")
    assert before.status_code == 200
    assert before.json()["folders"] == []

    source = tmp_path / "external-media"
    source.mkdir()
    updated = await client.patch(
        "/api/settings/folders",
        json={
            "folders": [
                {
                    "path": str(source),
                    "refresh_interval_seconds": 300,
                    "markers": [],
                }
            ]
        },
    )
    assert updated.status_code == 200

    from config import reload_settings
    reload_settings()
    response = await client.get("/api/settings")
    folder = response.json()["folders"][0]
    assert folder["path"] == str(source)
    assert "readonly" not in folder
    assert "allow_generate" not in folder
    assert "is_uploads_folder" not in folder
    assert "uploads_subfolder" not in folder


@pytest.mark.asyncio
async def test_removing_source_immediately_hides_and_deactivates_its_media(
    client, db_session, tmp_path
):
    source = tmp_path / "watched"
    retained_source = tmp_path / "still-watched"
    source_file = source / "gone-from-library.png"
    retained_file = retained_source / "still-visible.png"
    source_hash = generate_test_image(source_file)
    retained_hash = generate_test_image(retained_file)

    response = await client.patch(
        "/api/settings/folders",
        json={
            "folders": [
                {"path": str(source), "markers": []},
                {"path": str(retained_source), "markers": []},
            ]
        },
    )
    assert response.status_code == 200
    reload_settings()

    async with db_session() as session:
        removed_media = await create_media_item(
            session,
            file_path=source_file,
            file_hash=source_hash,
            file_size=source_file.stat().st_size,
            metadata_status="completed",
            clip_status="pending",
        )
        retained_media = await create_media_item(
            session,
            file_path=retained_file,
            file_hash=retained_hash,
            file_size=retained_file.stat().st_size,
            metadata_status="completed",
            clip_status="pending",
        )
        _, removed_asset = await register_external_asset(session, media=removed_media)
        _, retained_asset = await register_external_asset(session, media=retained_media)
        await session.commit()
        removed_media_id = removed_media.id
        retained_media_id = retained_media.id
        removed_asset_id = removed_asset.id
        retained_asset_id = retained_asset.id

    before = await client.get("/api/assets/browse")
    assert before.status_code == 200
    assert {item["asset_id"] for item in before.json()["items"]} >= {
        removed_asset_id,
        retained_asset_id,
    }

    response = await client.patch(
        "/api/settings/folders",
        json={"folders": [{"path": str(retained_source), "markers": []}]},
    )
    assert response.status_code == 200
    assert response.json()["deactivated_media_count"] == 1

    after = await client.get("/api/assets/browse")
    assert after.status_code == 200
    visible_ids = {item["asset_id"] for item in after.json()["items"]}
    assert removed_asset_id not in visible_ids
    assert retained_asset_id in visible_ids

    async with db_session() as session:
        removed = await session.get(MediaItem, removed_media_id)
        retained = await session.get(MediaItem, retained_media_id)
        assert removed is not None
        assert removed.file_unavailable is True
        assert retained.file_unavailable is False
        eligible_count = await session.scalar(
            select(func.count(MediaItem.id)).where(
                MediaItem.id.in_([removed_media_id, retained_media_id]),
                media_eligible_for_background_work(),
            )
        )
        assert eligible_count == 1
