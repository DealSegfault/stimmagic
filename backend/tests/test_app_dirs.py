import app_dirs
from storage_service import managed_object_root


def test_asset_root_redirects_generated_and_managed_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("STIMMA_ASSET_ROOT", str(tmp_path / "minimax"))

    assert app_dirs.get_managed_staging_dir("profile-1", "generated") == (
        tmp_path / "minimax" / "staging" / "profile-1" / "generated"
    )
    assert managed_object_root("profile-1") == (
        tmp_path / "minimax" / "assets" / "profile-1" / "objects"
    )


def test_without_asset_root_storage_stays_in_profile_dir(monkeypatch):
    monkeypatch.delenv("STIMMA_ASSET_ROOT", raising=False)

    staging = app_dirs.get_managed_staging_dir("profile-1", "generated")
    objects = managed_object_root("profile-1")

    assert staging.parts[-3:] == ("profile-1", "staging", "generated")
    assert objects.parts[-2:] == ("profile-1", "objects")
