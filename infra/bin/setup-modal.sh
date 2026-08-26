#!/usr/bin/env bash
# ==============================================================================
# setup-modal.sh - Automated Modal & Containers Setup for ComfyUI / Stimma Agent
# ==============================================================================
# Usage:
#   ./infra/bin/setup-modal.sh
#   HF_TOKEN="hf_..." MODAL_TOKEN_ID="ak-..." MODAL_TOKEN_SECRET="as-..." ./infra/bin/setup-modal.sh
#   ./infra/bin/setup-modal.sh --hf-token "hf_..." --modal-token-id "ak-..." --modal-token-secret "as-..."
# ==============================================================================

set -euo pipefail

INFRA_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$INFRA_ROOT/.." && pwd)"
CONFIG_DIR="$HOME/.config/adp-comfy"
PROXY_TOKEN_FILE="$CONFIG_DIR/modal-proxy-token.json"

COLOR_BLUE="\033[1;34m"
COLOR_GREEN="\033[1;32m"
COLOR_YELLOW="\033[1;33m"
COLOR_RED="\033[1;31m"
COLOR_CYAN="\033[1;36m"
COLOR_RESET="\033[0m"

log_info() {
  printf "${COLOR_BLUE}[INFO]${COLOR_RESET} %s\n" "$1"
}

log_success() {
  printf "${COLOR_GREEN}[SUCCESS]${COLOR_RESET} %s\n" "$1"
}

log_warn() {
  printf "${COLOR_YELLOW}[WARN]${COLOR_RESET} %s\n" "$1"
}

log_error() {
  printf "${COLOR_RED}[ERROR]${COLOR_RESET} %s\n" "$1" >&2
}

log_step() {
  printf "\n${COLOR_CYAN}==> %s${COLOR_RESET}\n" "$1"
}

# CLI Flags
CLI_HF_TOKEN="${HF_TOKEN:-}"
CLI_MODAL_TOKEN_ID="${MODAL_TOKEN_ID:-}"
CLI_MODAL_TOKEN_SECRET="${MODAL_TOKEN_SECRET:-}"
SKIP_DOWNLOADS=0
SKIP_LIPSYNC=0
SKIP_TRELLIS2=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -i|--interactive)
      exec python3 "$INFRA_ROOT/bin/setup-interactive.py"
      ;;
    --hf-token)
      CLI_HF_TOKEN="$2"
      shift 2
      ;;
    --modal-token-id)
      CLI_MODAL_TOKEN_ID="$2"
      shift 2
      ;;
    --modal-token-secret)
      CLI_MODAL_TOKEN_SECRET="$2"
      shift 2
      ;;
    --skip-downloads)
      SKIP_DOWNLOADS=1
      shift
      ;;
    --skip-lipsync)
      SKIP_LIPSYNC=1
      shift
      ;;
    --skip-trellis2)
      SKIP_TRELLIS2=1
      shift
      ;;
    -h|--help)
      echo "Usage: ./infra/bin/setup-modal.sh [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  -i, --interactive             Launch interactive setup wizard (recommandé pour CLI/Codex)"
      echo "  --hf-token <TOKEN>            Hugging Face Read Token (for FLUX Fill / H3)"
      echo "  --modal-token-id <ID>         Modal Token ID (ak-...)"
      echo "  --modal-token-secret <SECRET> Modal Token Secret (as-...)"
      echo "  --skip-downloads              Skip pre-populating Modal volumes"
      echo "  --skip-lipsync                Skip deploying Maya LatentSync"
      echo "  --skip-trellis2               Skip deploying TRELLIS.2 image-to-3D"
      echo "  -h, --help                    Show this help message"
      exit 0
      ;;
    *)
      log_error "Argument inconnu : $1"
      exit 1
      ;;
  esac
done

printf "${COLOR_BLUE}"
cat << "EOF"
===================================================================
     MODAL CLOUD CONTAINERS AUTO-SETUP FOR COMFYUI / STIMMA
===================================================================
EOF
printf "${COLOR_RESET}"

# 1. Verification des prérequis (Python, Modal CLI, jq)
log_step "1/6 : Vérification des dépendances locales"

if ! command -v python3 >/dev/null 2>&1; then
  log_error "Python 3 est requis mais introuvable."
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  log_warn "'jq' n'est pas détecté. Tentative d'utilisation des outils de secours intégrés."
fi

# Résolution de la commande modal
if ! command -v modal >/dev/null 2>&1; then
  if [ -x "$HOME/.local/share/uv/tools/modal/bin/modal" ]; then
    export PATH="$HOME/.local/share/uv/tools/modal/bin:$PATH"
  else
    log_info "Modal CLI non trouvé. Installation en cours via pip..."
    python3 -m pip install --upgrade modal || {
      log_error "Échec de l'installation de Modal CLI. Installez-le avec : pip install modal ou uv tool install modal"
      exit 1
    }
  fi
fi

log_success "Modal CLI opérationnel : $(modal --version 2>/dev/null || echo 'modal')"

# 2. Authentification Modal
log_step "2/6 : Configuration de l'authentification Modal"

if [ -n "$CLI_MODAL_TOKEN_ID" ] && [ -n "$CLI_MODAL_TOKEN_SECRET" ]; then
  log_info "Enregistrement des clés Modal fournies..."
  modal token set --token-id "$CLI_MODAL_TOKEN_ID" --token-secret "$CLI_MODAL_TOKEN_SECRET"
  log_success "Token Modal configuré."
else
  # Vérifier si déjà authentifié
  if modal profile current >/dev/null 2>&1; then
    log_success "Session Modal déjà active ($(modal profile current | head -n1))."
  else
    log_warn "Aucun token Modal actif."
    echo -n "Entrez votre Modal Token ID (ak-...) : "
    read -r CLI_MODAL_TOKEN_ID
    echo -n "Entrez votre Modal Token Secret (as-...) : "
    read -r -s CLI_MODAL_TOKEN_SECRET
    echo ""
    if [ -z "$CLI_MODAL_TOKEN_ID" ] || [ -z "$CLI_MODAL_TOKEN_SECRET" ]; then
      log_error "Modal Token ID et Secret sont requis."
      exit 1
    fi
    modal token set --token-id "$CLI_MODAL_TOKEN_ID" --token-secret "$CLI_MODAL_TOKEN_SECRET"
    log_success "Token Modal configuré avec succès."
  fi
fi

# 3. Configuration du Token Hugging Face
log_step "3/6 : Configuration du Secret Hugging Face sur Modal"

if [ -z "$CLI_HF_TOKEN" ]; then
  if [ -n "${HF_TOKEN:-}" ]; then
    CLI_HF_TOKEN="$HF_TOKEN"
  else
    echo -n "Entrez votre Hugging Face Token (hf_...) : "
    read -r -s CLI_HF_TOKEN
    echo ""
  fi
fi

if [ -z "$CLI_HF_TOKEN" ]; then
  log_warn "Aucun HF_TOKEN fourni. Le téléchargement de modèles sous licence (FLUX.1-Fill-dev) risque d'échouer."
else
  log_info "Création du secret Modal 'huggingface'..."
  modal secret create huggingface HF_TOKEN="$CLI_HF_TOKEN" --force >/dev/null 2>&1 || {
    # Si --force non supporté par la version installée
    modal secret create huggingface HF_TOKEN="$CLI_HF_TOKEN" || true
  }
  log_success "Secret Modal 'huggingface' configuré."
fi

# 4. Configuration du Token Proxy Local (Sécurisation ComfyUI & Repaint)
log_step "4/6 : Configuration des Tokens Proxy de sécurité"

mkdir -p "$CONFIG_DIR"
if [ -f "$PROXY_TOKEN_FILE" ] && python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["Modal-Key"].startswith("wk-") and d["Modal-Secret"].startswith("ws-")' "$PROXY_TOKEN_FILE" 2>/dev/null; then
  log_success "Proxy Token Modal existant : $PROXY_TOKEN_FILE"
else
  if [ -f "$PROXY_TOKEN_FILE" ]; then
    log_warn "Le fichier proxy existant n'est pas un Token Modal wk-/ws- valide ; il sera remplacé."
  fi
  log_info "Création d'un Proxy Token dans le workspace Modal..."
  PROXY_JSON=$(modal workspace proxy-tokens create --json) || {
    log_error "Impossible de créer le Proxy Token Modal."
    exit 1
  }
  umask 077
  printf '%s' "$PROXY_JSON" | python3 -c 'import json,sys; d=json.load(sys.stdin); token={"Modal-Key":d["Modal-Key"],"Modal-Secret":d["Modal-Secret"]}; assert token["Modal-Key"].startswith("wk-") and token["Modal-Secret"].startswith("ws-"); open(sys.argv[1], "w").write(json.dumps(token, indent=2)+"\n")' "$PROXY_TOKEN_FILE" || {
    log_error "Modal a renvoyé un Proxy Token dans un format inattendu."
    exit 1
  }
  unset PROXY_JSON
  chmod 600 "$PROXY_TOKEN_FILE"
  log_success "Proxy Token Modal enregistré localement : $PROXY_TOKEN_FILE"
fi

# 5. Déploiement des Applications Modal
log_step "5/6 : Déploiement des conteneurs Modal (Scale-to-Zero)"

log_info "1. Déploiement ComfyUI + MiniMax H3 + MiniMax Music 3 (RTX PRO 6000 + B300 HD)..."
cd "$INFRA_ROOT"
modal deploy --strategy recreate modal_h3.py
log_success "Application 'comfyui-minimax-h3' déployée."

log_info "2. Déploiement FLUX.1 Fill Repaint Service (NVIDIA L40S)..."
cd "$REPO_ROOT"
modal deploy cloud_repaint/repaint_service.py
log_success "Application 'stimma-flux-fill' déployée."

if [ "$SKIP_LIPSYNC" -eq 0 ]; then
  log_info "3. Déploiement Maya LatentSync 1.6 LipSync (RTX PRO 6000)..."
  cd "$INFRA_ROOT"
  modal deploy modal_latentsync.py
  log_success "Application 'maya-latentsync' déployée."
fi

if [ "$SKIP_TRELLIS2" -eq 0 ]; then
  log_info "4. Déploiement TRELLIS.2 Image-to-3D (H100/H200)..."
  cd "$INFRA_ROOT"
  modal deploy modal_trellis2.py
  log_success "Application 'stimma-trellis2' déployée."
fi

# 6. Téléchargement des Poids dans les Volumes Modal
if [ "$SKIP_DOWNLOADS" -eq 0 ]; then
  log_step "6/6 : Initialisation des Volumes Modal (Téléchargement direct dans le Cloud)"
  log_info "Téléchargement des modèles MiniMax H3..."
  cd "$INFRA_ROOT"
  modal run modal_h3.py::download_models
  log_info "Téléchargement des modèles H3 full BF16 pour le worker B300 HD..."
  modal run modal_h3.py::download_hd_models
  
  log_info "Téléchargement des modèles MiniMax Music 3..."
  modal run modal_h3.py::download_music_models

  if [ -n "$CLI_HF_TOKEN" ]; then
    log_info "Téléchargement des modèles FLUX.1 Fill..."
    cd "$REPO_ROOT"
    modal run cloud_repaint/repaint_service.py::download_models
  fi

  if [ "$SKIP_LIPSYNC" -eq 0 ]; then
    log_info "Téléchargement des modèles LatentSync..."
    cd "$INFRA_ROOT"
    modal run modal_latentsync.py::download_models
  fi

  if [ "$SKIP_TRELLIS2" -eq 0 ]; then
    log_info "Téléchargement des modèles TRELLIS.2..."
    cd "$INFRA_ROOT"
    modal run modal_trellis2.py::download_models
  fi

  log_info "Vérification de l'inventaire distant..."
  cd "$INFRA_ROOT"
  modal run modal_h3.py::model_inventory
else
  log_info "Téléchargement des poids ignoré (--skip-downloads)."
fi

printf "${COLOR_GREEN}"
cat << "EOF"
===================================================================
     INSTALLATION MODAL ET DÉPLOIEMENT TERMINÉS AVEC SUCCÈS !
===================================================================
EOF
printf "${COLOR_RESET}"

echo ""
echo "Prochaines étapes pour démarrer :"
echo "  1. Lancer la passerelle locale : infra/bin/start-gateway.sh"
echo "  2. Lancer l'interface Stimma    : infra/bin/start-stimma.sh"
echo "  3. Suivre l'état et les coûts   : infra/bin/status.sh"
echo ""
