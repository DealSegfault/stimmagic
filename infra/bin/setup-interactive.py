#!/usr/bin/env python3
"""Interactive Modal & Agent Setup Wizard for ComfyUI / Stimma / Codex.

Guides users or code-agents (Codex CLI / Antigravity / Claude Code) through setting
up Modal credentials, Hugging Face tokens, deploying cloud GPU containers, and
pre-populating cloud storage volumes with zero local disk usage.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

# ANSI Colors
BOLD = "\033[1m"
GREEN = "\033[1;32m"
BLUE = "\033[1;34m"
YELLOW = "\033[1;33m"
CYAN = "\033[1;36m"
RED = "\033[1;31m"
DIM = "\033[2m"
RESET = "\033[0m"

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path.home() / ".config" / "adp-comfy"
PROXY_TOKEN_FILE = CONFIG_DIR / "modal-proxy-token.json"


def print_banner() -> None:
    print(f"\n{BLUE}{BOLD}╔════════════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BLUE}{BOLD}║         MODAL + COMFYUI + STIMMA AGENT SETUP WIZARD            ║{RESET}")
    print(f"{BLUE}{BOLD}╚════════════════════════════════════════════════════════════════╝{RESET}\n")


def log_step(step: int, total: int, title: str) -> None:
    print(f"\n{CYAN}{BOLD}[Étape {step}/{total}] ─── {title} ───{RESET}")


def log_info(msg: str) -> None:
    print(f"{BLUE}ℹ{RESET} {msg}")


def log_success(msg: str) -> None:
    print(f"{GREEN}✔{RESET} {msg}")


def log_warn(msg: str) -> None:
    print(f"{YELLOW}▲{RESET} {msg}")


def log_error(msg: str) -> None:
    print(f"{RED}✖{RESET} {msg}", file=sys.stderr)


def prompt_text(prompt: str, default: Optional[str] = None, is_secret: bool = False) -> str:
    """Prompt user or fallback if running in non-interactive environment."""
    display_prompt = f"{BOLD}{prompt}{RESET}"
    if default:
        display_prompt += f" {DIM}(défaut: {default}){RESET}"
    display_prompt += ": "

    if not sys.stdin.isatty():
        return default or ""

    while True:
        try:
            if is_secret:
                value = getpass.getpass(display_prompt).strip()
            else:
                value = input(display_prompt).strip()
            if not value and default is not None:
                return default
            if value:
                return value
        except (KeyboardInterrupt, EOFError):
            print("\nAnnulation par l'utilisateur.")
            sys.exit(130)


def prompt_bool(prompt: str, default: bool = True) -> bool:
    choice_str = "[O/n]" if default else "[o/N]"
    if not sys.stdin.isatty():
        return default
    resp = input(f"{BOLD}{prompt}{RESET} {DIM}{choice_str}{RESET} ").strip().lower()
    if not resp:
        return default
    return resp in ("o", "oui", "y", "yes", "true", "1")


def run_cmd(cmd: list[str], cwd: Optional[Path] = None, capture: bool = False, env: Optional[dict] = None) -> tuple[int, str]:
    """Execute command with optional output capture."""
    exec_env = os.environ.copy()
    if env:
        exec_env.update(env)
    
    if capture:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd or ROOT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=exec_env,
        )
        return proc.returncode, proc.stdout + proc.stderr
    else:
        proc = subprocess.run(cmd, cwd=str(cwd or ROOT_DIR), env=exec_env)
        return proc.returncode, ""


def check_modal_cli() -> str:
    """Verify modal executable exists or install it."""
    modal_bin = shutil.which("modal")
    if not modal_bin:
        uv_modal = Path.home() / ".local" / "share" / "uv" / "tools" / "modal" / "bin" / "modal"
        if uv_modal.exists():
            modal_bin = str(uv_modal)
    
    if not modal_bin:
        log_warn("Modal CLI n'est pas encore installé.")
        if prompt_bool("Voulez-vous installer 'modal' automatiquement via pip ?"):
            log_info("Installation de modal...")
            code, out = run_cmd([sys.executable, "-m", "pip", "install", "--upgrade", "modal"])
            if code != 0:
                log_error(f"Échec de l'installation de modal :\n{out}")
                sys.exit(1)
            modal_bin = shutil.which("modal") or str(Path(sys.executable).parent / "modal")
            log_success("Modal CLI installé avec succès.")
        else:
            log_error("Modal CLI est requis pour continuer. Installez-le avec : pip install modal")
            sys.exit(1)
    return modal_bin


def setup_modal_auth(modal_bin: str, token_id: Optional[str] = None, token_secret: Optional[str] = None) -> tuple[str, str]:
    """Check or configure Modal credentials."""
    # Check if already authenticated
    code, out = run_cmd([modal_bin, "profile", "current"], capture=True)
    is_active = (code == 0 and "profile" in out.lower() and not "no profile" in out.lower())

    if is_active and not (token_id and token_secret):
        log_success(f"Session Modal déjà active ({out.strip()}).")
        if not prompt_bool("Voulez-vous réutiliser cette session existante ?"):
            token_id = prompt_text("Modal Token ID (ak-...)")
            token_secret = prompt_text("Modal Token Secret (as-...)", is_secret=True)
            run_cmd([modal_bin, "token", "set", "--token-id", token_id, "--token-secret", token_secret])
            log_success("Nouveaux identifiants Modal configurés.")
    else:
        if not token_id:
            token_id = prompt_text("Modal Token ID (ak-...)")
        if not token_secret:
            token_secret = prompt_text("Modal Token Secret (as-...)", is_secret=True)
        code, out = run_cmd([modal_bin, "token", "set", "--token-id", token_id, "--token-secret", token_secret], capture=True)
        if code != 0:
            log_error(f"Erreur lors de la configuration du token Modal : {out}")
            sys.exit(1)
        log_success("Identifiants Modal configurés.")

    return token_id or "", token_secret or ""


def setup_huggingface_secret(modal_bin: str, hf_token: Optional[str] = None) -> str:
    """Create or update Hugging Face secret on Modal."""
    if not hf_token:
        hf_token = os.environ.get("HF_TOKEN") or prompt_text("Hugging Face Read Token (hf_...)", is_secret=True)
    
    if not hf_token:
        log_warn("Aucun HF_TOKEN fourni. Le téléchargement de modèles comme FLUX.1 Fill pourrait échouer.")
        return ""

    log_info("Création du secret 'huggingface' sur Modal...")
    code, out = run_cmd([modal_bin, "secret", "create", "huggingface", f"HF_TOKEN={hf_token}", "--force"], capture=True)
    if code != 0:
        # Fallback if --force flag not supported in older modal CLI
        code, out = run_cmd([modal_bin, "secret", "create", "huggingface", f"HF_TOKEN={hf_token}"], capture=True)
    
    if code == 0 or "already exists" in out.lower():
        log_success("Secret 'huggingface' configuré sur Modal.")
    else:
        log_warn(f"Note lors de la création du secret : {out.strip()}")
    return hf_token


def setup_local_proxy_keys() -> None:
    """Ensure ~/.config/adp-comfy/modal-proxy-token.json is valid."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not PROXY_TOKEN_FILE.exists():
        log_info("Génération de clés proxy locales sécurisées...")
        key = f"key_{secrets.token_hex(16)}"
        secret = f"sec_{secrets.token_hex(24)}"
        PROXY_TOKEN_FILE.write_text(
            json.dumps({"Modal-Key": key, "Modal-Secret": secret}, indent=2),
            encoding="utf-8",
        )
        PROXY_TOKEN_FILE.chmod(0o600)
        log_success(f"Fichier de clés proxy généré : {PROXY_TOKEN_FILE}")
    else:
        log_success(f"Fichier de clés proxy existant : {PROXY_TOKEN_FILE}")


def deploy_apps(modal_bin: str, deploy_h3: bool = True, deploy_repaint: bool = True, deploy_latentsync: bool = True) -> None:
    """Deploy Modal serverless applications."""
    if deploy_h3:
        log_info("1. Déploiement ComfyUI + MiniMax H3 + Music 3 (RTX PRO 6000)...")
        code, out = run_cmd([modal_bin, "deploy", "--strategy", "recreate", "modal_h3.py"], cwd=ROOT_DIR)
        if code != 0:
            log_error("Erreur lors du déploiement de comfyui-minimax-h3.")
        else:
            log_success("comfyui-minimax-h3 déployé.")

    if deploy_repaint:
        log_info("2. Déploiement FLUX.1 Fill Repaint (NVIDIA L40S)...")
        code, out = run_cmd([modal_bin, "deploy", "cloud_repaint/repaint_service.py"], cwd=ROOT_DIR / "stimma")
        if code != 0:
            log_error("Erreur lors du déploiement de stimma-flux-fill.")
        else:
            log_success("stimma-flux-fill déployé.")

    if deploy_latentsync:
        log_info("3. Déploiement Maya LatentSync 1.6 LipSync (RTX PRO 6000)...")
        code, out = run_cmd([modal_bin, "deploy", "modal_latentsync.py"], cwd=ROOT_DIR)
        if code != 0:
            log_error("Erreur lors du déploiement de maya-latentsync.")
        else:
            log_success("maya-latentsync déployé.")


def populate_volumes(modal_bin: str, has_hf_token: bool, download_h3: bool = True, download_repaint: bool = True, download_latentsync: bool = True) -> None:
    """Pre-download weights directly into Modal cloud storage."""
    log_info("Initialisation des poids distants (0 Go téléchargés en local)...")

    if download_h3:
        log_info("Téléchargement des poids MiniMax H3...")
        run_cmd([modal_bin, "run", "modal_h3.py::download_models"], cwd=ROOT_DIR)
        log_info("Téléchargement des poids H3 full BF16 pour le worker B300 HD...")
        run_cmd([modal_bin, "run", "modal_h3.py::download_hd_models"], cwd=ROOT_DIR)
        log_info("Téléchargement des poids MiniMax Music 3...")
        run_cmd([modal_bin, "run", "modal_h3.py::download_music_models"], cwd=ROOT_DIR)

    if download_repaint and has_hf_token:
        log_info("Téléchargement des poids FLUX.1 Fill Dev...")
        run_cmd([modal_bin, "run", "cloud_repaint/repaint_service.py::download_models"], cwd=ROOT_DIR / "stimma")

    if download_latentsync:
        log_info("Téléchargement des poids LatentSync...")
        run_cmd([modal_bin, "run", "modal_latentsync.py::download_models"], cwd=ROOT_DIR)

    log_info("Inventaire des modèles dans le volume Modal...")
    run_cmd([modal_bin, "run", "modal_h3.py::model_inventory"], cwd=ROOT_DIR)


def main() -> None:
    parser = argparse.ArgumentParser(description="Configuration Interactive Modal pour ComfyUI / Stimma Agent")
    parser.add_argument("--hf-token", help="Token Hugging Face")
    parser.add_argument("--modal-token-id", help="Modal Token ID")
    parser.add_argument("--modal-token-secret", help="Modal Token Secret")
    parser.add_argument("--non-interactive", action="store_true", help="Mode non interactif (utilise les arguments/variables)")
    parser.add_argument("--skip-downloads", action="store_true", help="Ne pas exécuter les téléchargements de modèles distants")
    args = parser.parse_args()

    print_banner()

    TOTAL_STEPS = 6

    # 1. Verification Modal CLI
    log_step(1, TOTAL_STEPS, "Vérification de l'environnement CLI")
    modal_bin = check_modal_cli()
    log_success(f"Modal CLI disponible : {modal_bin}")

    # 2. Authentification Modal
    log_step(2, TOTAL_STEPS, "Authentification Modal")
    token_id = args.modal_token_id or os.environ.get("MODAL_TOKEN_ID")
    token_secret = args.modal_token_secret or os.environ.get("MODAL_TOKEN_SECRET")
    setup_modal_auth(modal_bin, token_id, token_secret)

    # 3. Secret Hugging Face
    log_step(3, TOTAL_STEPS, "Configuration Hugging Face (Secret Modal)")
    hf_token = setup_huggingface_secret(modal_bin, args.hf_token)

    # 4. Clés Proxy Locales
    log_step(4, TOTAL_STEPS, "Sécurisation de la Passerelle Proxy")
    setup_local_proxy_keys()

    # 5. Déploiement Conteneurs
    log_step(5, TOTAL_STEPS, "Déploiement des Applications Modal (Scale-to-Zero)")
    deploy_h3 = True
    deploy_repaint = True
    deploy_latentsync = True

    if not args.non_interactive and sys.stdin.isatty():
        deploy_h3 = prompt_bool("Déployer ComfyUI MiniMax H3 & Music 3 ?", True)
        deploy_repaint = prompt_bool("Déployer FLUX.1 Fill Repaint ?", True)
        deploy_latentsync = prompt_bool("Déployer Maya LatentSync 1.6 ?", True)

    deploy_apps(modal_bin, deploy_h3, deploy_repaint, deploy_latentsync)

    # 6. Volumes
    log_step(6, TOTAL_STEPS, "Initialisation des Volumes Distants")
    if args.skip_downloads:
        log_info("Téléchargement ignoré (--skip-downloads).")
    else:
        do_download = True
        if not args.non_interactive and sys.stdin.isatty():
            do_download = prompt_bool("Télécharger immédiatement les modèles dans les Volumes Modal ?", True)
        if do_download:
            populate_volumes(modal_bin, bool(hf_token), deploy_h3, deploy_repaint, deploy_latentsync)

    # Résumé
    print(f"\n{GREEN}{BOLD}════════════════════════════════════════════════════════════════{RESET}")
    print(f"{GREEN}{BOLD}             CONFIGURATION MODAL TERMINÉE AVEC SUCCÈS !          {RESET}")
    print(f"{GREEN}{BOLD}════════════════════════════════════════════════════════════════{RESET}\n")
    print(f"Pour démarrer votre environnement de travail :")
    print(f"  {CYAN}1. Démarrer la passerelle locale :{RESET}  bin/start-gateway.sh")
    print(f"  {CYAN}2. Démarrer l'interface Stimma    :{RESET}  bin/start-stimma.sh")
    print(f"  {CYAN}3. Vérifier l'état & les coûts    :{RESET}  bin/status.sh\n")


if __name__ == "__main__":
    main()
