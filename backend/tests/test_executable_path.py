from executable_path import merge_path_entries


def test_merge_path_entries_adds_existing_distinct_directories():
    existing = {r"C:\Windows", r"C:\Tools", r"C:\Users\test\Gyan.FFmpeg_hash\bin"}

    result = merge_path_entries(
        r"C:\Windows;C:\Tools",
        [r"C:\Users\test\Gyan.FFmpeg_hash\bin", r"C:\Missing"],
        separator=";",
        path_exists=existing.__contains__,
        case_insensitive=True,
    )

    assert result == (
        r"C:\Windows;C:\Tools;C:\Users\test\Gyan.FFmpeg_hash\bin"
    )


def test_merge_path_entries_deduplicates_windows_paths_case_insensitively():
    result = merge_path_entries(
        r"C:\Windows;C:\Tools",
        [r"c:\tools", r'"C:\Windows"'],
        separator=";",
        path_exists=lambda _path: True,
        case_insensitive=True,
    )

    assert result == r"C:\Windows;C:\Tools"


def test_merge_path_entries_does_not_add_a_leading_separator():
    result = merge_path_entries(
        "",
        [r"C:\Tools"],
        separator=";",
        path_exists=lambda _path: True,
        case_insensitive=True,
    )

    assert result == r"C:\Tools"
