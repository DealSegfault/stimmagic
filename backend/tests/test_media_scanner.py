from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin

from exif_extractor import extract_prompt_from_exif
from media_scanner import fast_scan_directories, get_image_dimensions


def test_png_dimensions_and_prompt_do_not_request_absent_exif(tmp_path: Path, monkeypatch):
    image_path = tmp_path / "plain.png"
    Image.new("RGBA", (31, 17)).save(image_path)

    def fail_getexif(_image):
        raise AssertionError("ordinary PNG ingestion must not call getexif()")

    monkeypatch.setattr(PngImagePlugin.PngImageFile, "getexif", fail_getexif)

    assert get_image_dimensions(image_path) == (31, 17, True)
    assert extract_prompt_from_exif(image_path) == (None, None)


def test_image_dimensions_swap_header_values_for_exif_orientation(tmp_path: Path):
    image_path = tmp_path / "rotated.jpg"
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (31, 17)).save(image_path, exif=exif)

    assert get_image_dimensions(image_path) == (17, 31, False)


def test_png_prompt_chunk_is_still_extracted(tmp_path: Path):
    image_path = tmp_path / "prompt.png"
    info = PngImagePlugin.PngInfo()
    info.add_text("parameters", "a detailed test prompt with enough characters")
    Image.new("RGB", (2, 2)).save(image_path, pnginfo=info)

    assert extract_prompt_from_exif(image_path) == (
        "a detailed test prompt with enough characters",
        "a detailed test prompt with enough characters",
    )


@pytest.mark.asyncio
async def test_fast_scan_prunes_app_owned_storage_from_broad_source(tmp_path: Path):
    source = tmp_path / "source"
    external = source / "pictures" / "external.png"
    app_data = source / "Library" / "Stimma"
    staged = app_data / "profile" / "staging" / "generated" / "generated.png"
    managed = app_data / "profile" / "objects" / "media" / "1" / "generated.png"
    provider_asset = app_data / "cache" / "provider-assets" / "run" / "output.png"

    for path in (external, staged, managed, provider_asset):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"png")

    scanned, untrusted = await fast_scan_directories(
        [str(source)], excluded_paths=[app_data]
    )

    assert [item["file_path"] for item in scanned] == [str(external)]
    assert untrusted == set()


@pytest.mark.asyncio
async def test_fast_scan_rejects_source_inside_app_owned_storage(tmp_path: Path):
    app_data = tmp_path / "Stimma"
    generated = app_data / "profile" / "staging" / "generated" / "result.png"
    generated.parent.mkdir(parents=True)
    generated.write_bytes(b"png")

    scanned, untrusted = await fast_scan_directories(
        [str(generated.parent)], excluded_paths=[app_data]
    )

    assert scanned == []
    assert untrusted == {str(generated.parent)}


@pytest.mark.asyncio
async def test_fast_scan_rejects_temporary_transfer_tree(tmp_path: Path):
    transfer = tmp_path / "stimma-assets-old" / "result.png"
    transfer.parent.mkdir(parents=True)
    transfer.write_bytes(b"png")

    scanned, untrusted = await fast_scan_directories(
        [str(tmp_path)], excluded_paths=[tmp_path]
    )

    assert scanned == []
    assert untrusted == {str(tmp_path)}


@pytest.mark.asyncio
async def test_fast_scan_flags_missing_root_as_untrusted(tmp_path: Path):
    present = tmp_path / "present"
    present.mkdir()
    (present / "a.png").write_bytes(b"png")
    missing = tmp_path / "unmounted-volume"

    scanned, untrusted = await fast_scan_directories(
        [str(present), str(missing)], excluded_paths=[]
    )

    assert [item["file_path"] for item in scanned] == [str(present / "a.png")]
    assert untrusted == {str(missing)}


@pytest.mark.asyncio
async def test_fast_scan_flags_unreadable_root_as_untrusted(tmp_path: Path):
    import os

    if os.geteuid() == 0:
        pytest.skip("root bypasses directory permissions")

    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "a.png").write_bytes(b"png")
    locked.chmod(0o000)
    try:
        scanned, untrusted = await fast_scan_directories(
            [str(locked)], excluded_paths=[]
        )
    finally:
        locked.chmod(0o755)

    assert scanned == []
    assert untrusted == {str(locked)}


@pytest.mark.asyncio
async def test_fast_scan_limits_repeated_stat_warnings(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    broken = [source / f"broken-{index}.png" for index in range(10)]
    for path in broken:
        path.write_bytes(b"png")

    original_stat = Path.stat

    def fail_selected_paths(path: Path, *args, **kwargs):
        if path in broken:
            raise OSError("broken link")
        return original_stat(path, *args, **kwargs)

    warnings = []
    monkeypatch.setattr(Path, "stat", fail_selected_paths)
    monkeypatch.setattr("media_scanner.log.warning", warnings.append)

    scanned, untrusted = await fast_scan_directories([str(source)])

    assert scanned == []
    assert untrusted == set()
    assert len([message for message in warnings if "Cannot stat" in message]) == 3
    assert any(
        "Skipped 10 media entries" in message
        and "7 similar warnings suppressed" in message
        for message in warnings
    )
