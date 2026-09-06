#!/usr/bin/env python3
"""Create the platform Stimma launcher and finish the local handoff."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path


INFRA_ROOT = Path(__file__).resolve().parent.parent
LAUNCH_SCRIPT = INFRA_ROOT / "bin" / "launch-stimma.sh"
WINDOWS_LAUNCH_SCRIPT = INFRA_ROOT / "bin" / "launch-stimma-windows.cmd"
LAUNCHER_NAME = "Lancer Stimma.command"
WINDOWS_LAUNCHER_NAME = "Stimma.lnk"
MEMO_NAME = "STIMMA - Installation terminée.txt"
MEMO_TEXT = """Installation Stimma terminée

Un raccourci a été mis sur votre Bureau.
Stimma est lancé et prêt à générer votre première vidéo.

À l'avenir, double-cliquez sur le raccourci Stimma pour le relancer.
"""


def default_desktop_dir() -> Path:
    if sys.platform != "win32":
        return Path.home() / "Desktop"

    # Respect a redirected/localized Desktop (including OneDrive) instead of
    # assuming that it is always %USERPROFILE%\Desktop.
    import ctypes

    buffer = ctypes.create_unicode_buffer(260)
    result = ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buffer)
    if result == 0 and buffer.value:
        return Path(buffer.value)
    return Path.home() / "Desktop"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Installe le raccourci Stimma sur le Bureau."
    )
    parser.add_argument(
        "--desktop-dir",
        type=Path,
        default=default_desktop_dir(),
        help="Bureau cible (par défaut : ~/Desktop)",
    )
    parser.add_argument(
        "--no-launch",
        action="store_true",
        help="Crée uniquement le raccourci, sans lancer Stimma ni écrire le mémo.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if sys.platform == "win32":
        return install_windows_launcher(args)
    if sys.platform != "darwin" and args.desktop_dir == default_desktop_dir():
        print("Raccourci ignoré : cette étape est réservée à macOS et Windows.")
        return 0

    if not LAUNCH_SCRIPT.is_file():
        print(f"Script de lancement introuvable : {LAUNCH_SCRIPT}", file=sys.stderr)
        return 1

    desktop_dir = args.desktop_dir.expanduser().resolve()
    desktop_dir.mkdir(parents=True, exist_ok=True)
    launcher_path = desktop_dir / LAUNCHER_NAME
    launcher_path.write_text(
        "#!/bin/zsh\n"
        "set -eu\n"
        f"exec {shlex.quote(str(LAUNCH_SCRIPT))}\n",
        encoding="utf-8",
    )
    launcher_path.chmod(0o755)
    print(f"Raccourci créé : {launcher_path}")

    if args.no_launch:
        print("Lancement et mémo ignorés (--no-launch).")
        return 0

    launch_env = os.environ.copy()
    for secret_name in ("MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET", "HF_TOKEN"):
        launch_env.pop(secret_name, None)
    completed = subprocess.run(
        [str(LAUNCH_SCRIPT)],
        cwd=str(INFRA_ROOT.parent),
        env=launch_env,
    )
    if completed.returncode != 0:
        print(
            "Le raccourci est installé, mais Stimma n'est pas encore prêt ; "
            "aucun mémo de réussite n'a été écrit.",
            file=sys.stderr,
        )
        return completed.returncode

    memo_path = desktop_dir / MEMO_NAME
    memo_path.write_text(MEMO_TEXT, encoding="utf-8")
    memo_path.chmod(0o644)
    print(f"Mémo créé : {memo_path}")
    return 0


def install_windows_launcher(args: argparse.Namespace) -> int:
    if not WINDOWS_LAUNCH_SCRIPT.is_file():
        print(
            f"Lanceur Windows introuvable : {WINDOWS_LAUNCH_SCRIPT}",
            file=sys.stderr,
        )
        return 1

    desktop_dir = args.desktop_dir.expanduser().resolve()
    desktop_dir.mkdir(parents=True, exist_ok=True)
    launcher_path = desktop_dir / WINDOWS_LAUNCHER_NAME
    icon_path = INFRA_ROOT.parent / "src-tauri" / "icons" / "icon.ico"

    powershell_script = r"""
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($env:STIMMA_SHORTCUT_PATH)
$shortcut.TargetPath = Join-Path $env:SystemRoot 'System32\cmd.exe'
$shortcut.Arguments = '/d /c "' + $env:STIMMA_WINDOWS_LAUNCHER + '"'
$shortcut.WorkingDirectory = $env:STIMMA_REPO_ROOT
$shortcut.Description = 'Démarrer Stimma — passerelle, backend, frontend et application'
if (Test-Path -LiteralPath $env:STIMMA_ICON_PATH) {
    $shortcut.IconLocation = $env:STIMMA_ICON_PATH + ',0'
}
$shortcut.Save()
"""
    shortcut_env = os.environ.copy()
    shortcut_env.update(
        {
            "STIMMA_SHORTCUT_PATH": str(launcher_path),
            "STIMMA_WINDOWS_LAUNCHER": str(WINDOWS_LAUNCH_SCRIPT),
            "STIMMA_REPO_ROOT": str(INFRA_ROOT.parent),
            "STIMMA_ICON_PATH": str(icon_path),
        }
    )
    for secret_name in ("MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET", "HF_TOKEN"):
        shortcut_env.pop(secret_name, None)
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            powershell_script,
        ],
        env=shortcut_env,
        check=False,
    )
    if completed.returncode != 0:
        print("Impossible de créer le raccourci Windows Stimma.", file=sys.stderr)
        return completed.returncode

    print(f"Raccourci créé : {launcher_path}")
    if args.no_launch:
        print("Lancement et mémo ignorés (--no-launch).")
        return 0

    launch_env = os.environ.copy()
    for secret_name in ("MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET", "HF_TOKEN"):
        launch_env.pop(secret_name, None)
    completed = subprocess.run(
        ["cmd.exe", "/d", "/c", str(WINDOWS_LAUNCH_SCRIPT)],
        cwd=str(INFRA_ROOT.parent),
        env=launch_env,
        check=False,
    )
    if completed.returncode != 0:
        print(
            "Le raccourci est installé, mais Stimma n'est pas encore prêt ; "
            "aucun mémo de réussite n'a été écrit.",
            file=sys.stderr,
        )
        return completed.returncode

    memo_path = desktop_dir / MEMO_NAME
    memo_path.write_text(MEMO_TEXT, encoding="utf-8")
    print(f"Mémo créé : {memo_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
