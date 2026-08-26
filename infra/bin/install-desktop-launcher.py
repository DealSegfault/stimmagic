#!/usr/bin/env python3
"""Create the macOS Stimma launcher and finish the local handoff."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path


INFRA_ROOT = Path(__file__).resolve().parent.parent
LAUNCH_SCRIPT = INFRA_ROOT / "bin" / "launch-stimma.sh"
LAUNCHER_NAME = "Lancer Stimma.command"
MEMO_NAME = "STIMMA - Installation terminée.txt"
MEMO_TEXT = """Installation Stimma terminée

Un raccourci « Lancer Stimma.command » a été mis sur votre Bureau.
Stimma est lancé et prêt à générer votre première vidéo.

À l'avenir, double-cliquez sur « Lancer Stimma.command » pour le relancer.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Installe le raccourci macOS de Stimma sur le Bureau."
    )
    parser.add_argument(
        "--desktop-dir",
        type=Path,
        default=Path.home() / "Desktop",
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
    if sys.platform != "darwin" and args.desktop_dir == Path.home() / "Desktop":
        print("Raccourci .command ignoré : cette étape est réservée à macOS.")
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


if __name__ == "__main__":
    raise SystemExit(main())
