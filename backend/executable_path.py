"""Make user-installed command-line tools visible to the desktop backend."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, MutableMapping


def _path_key(path: str, *, case_insensitive: bool) -> str:
    normalized = os.path.normpath(path)
    return normalized.casefold() if case_insensitive else normalized


def merge_path_entries(
    current_path: str,
    candidates: Iterable[str],
    *,
    separator: str = os.pathsep,
    path_exists: Callable[[str], bool] = os.path.isdir,
    case_insensitive: bool = os.name == "nt",
) -> str:
    """Append existing, distinct directories to a PATH value."""
    entries = [entry for entry in current_path.split(separator) if entry]
    seen = {
        _path_key(entry.strip().strip('"'), case_insensitive=case_insensitive)
        for entry in entries
        if entry.strip().strip('"')
    }

    for candidate in candidates:
        candidate = candidate.strip().strip('"')
        if not candidate:
            continue
        candidate = os.path.expandvars(candidate)
        key = _path_key(candidate, case_insensitive=case_insensitive)
        if key in seen or not path_exists(candidate):
            continue
        entries.append(candidate)
        seen.add(key)

    return separator.join(entries)


def _windows_registry_path_entries() -> list[str]:
    """Read the current Machine and User PATH values from the registry."""
    try:
        import winreg
    except ImportError:
        return []

    locations = (
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ),
        (winreg.HKEY_CURRENT_USER, r"Environment"),
    )
    entries: list[str] = []
    for root, subkey in locations:
        try:
            with winreg.OpenKey(root, subkey) as key:
                value, _value_type = winreg.QueryValueEx(key, "Path")
        except OSError:
            continue
        if isinstance(value, str):
            entries.extend(value.split(";"))
    return entries


def augment_executable_path(
    environ: MutableMapping[str, str] | None = None,
) -> None:
    """Refresh PATH locations needed by tools such as FFmpeg.

    Desktop processes can retain an old environment after an installer updates
    Windows' registry-backed PATH. Read those live values at each backend start
    so a newly launched Stimma sees tools installed into versioned WinGet paths.
    """
    environ = os.environ if environ is None else environ
    candidates: list[str]
    if os.name == "nt":
        candidates = _windows_registry_path_entries()
        candidates.extend(
            [
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links"),
                os.path.expandvars(r"%ProgramFiles%\ffmpeg\bin"),
                (
                    os.path.expandvars(r"%ChocolateyInstall%\bin")
                    if os.environ.get("ChocolateyInstall")
                    else ""
                ),
            ]
        )
    else:
        candidates = [
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/opt/local/bin",
        ]

    environ["PATH"] = merge_path_entries(
        environ.get("PATH", ""),
        candidates,
        separator=os.pathsep,
        case_insensitive=os.name == "nt",
    )
