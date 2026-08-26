#!/bin/sh
set -eu

INFRA_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$INFRA_ROOT/.." && pwd)"
RUNTIME_ROOT="${STIMMA_RUNTIME_DIR:-$INFRA_ROOT/.runtime}"
COMFY_ROOT="$RUNTIME_ROOT/ComfyUI"
PLUGIN_LINK="$COMFY_ROOT/custom_nodes/ComfyUI-Stimma"
PLUGIN_SOURCE="$REPO_ROOT/custom_nodes/ComfyUI-Stimma"
COMFY_REVISION="0f1fa67ad8a68b62c65ebc97a7bf485df2459c3a"

fail() {
  echo "Erreur : $1" >&2
  exit 1
}

for command_name in git uv codex; do
  command -v "$command_name" >/dev/null 2>&1 || fail "$command_name est requis sur PATH."
done

if ! codex login status >/dev/null 2>&1; then
  fail "Codex CLI n'est pas connecté. Lancez 'codex', puis choisissez Sign in with ChatGPT."
fi

mkdir -p "$RUNTIME_ROOT"
if [ ! -d "$COMFY_ROOT/.git" ]; then
  if [ -e "$COMFY_ROOT" ]; then
    fail "$COMFY_ROOT existe déjà mais n'est pas un checkout Git ComfyUI."
  fi
  echo "Clonage du runtime ComfyUI dans $COMFY_ROOT..."
  git clone https://github.com/Comfy-Org/ComfyUI.git "$COMFY_ROOT"
fi

echo "Alignement de ComfyUI sur la révision testée..."
git -C "$COMFY_ROOT" fetch --quiet origin "$COMFY_REVISION"
git -C "$COMFY_ROOT" checkout --quiet "$COMFY_REVISION"

if [ ! -x "$COMFY_ROOT/.venv/bin/python" ]; then
  uv venv --python 3.12 "$COMFY_ROOT/.venv"
fi

echo "Installation des dépendances locales (aucun poids de modèle GPU)..."
uv pip install --python "$COMFY_ROOT/.venv/bin/python" \
  -r "$COMFY_ROOT/requirements.txt" \
  -r "$PLUGIN_SOURCE/requirements.txt" \
  modal

mkdir -p "$COMFY_ROOT/custom_nodes"
if [ -L "$PLUGIN_LINK" ]; then
  current_target=$(readlink "$PLUGIN_LINK")
  if [ "$current_target" != "$PLUGIN_SOURCE" ]; then
    unlink "$PLUGIN_LINK"
  fi
elif [ -e "$PLUGIN_LINK" ]; then
  fail "$PLUGIN_LINK existe déjà et n'est pas un lien symbolique."
fi
if [ ! -e "$PLUGIN_LINK" ]; then
  ln -s "$PLUGIN_SOURCE" "$PLUGIN_LINK"
fi

echo ""
echo "Bootstrap local terminé. Aucun compte Stimma ni clé API LLM n'est requis."
echo "Codex CLI : connecté via ChatGPT"
echo "Étape Modal : infra/bin/setup-modal.sh --interactive"
echo "Cette étape installe 'Lancer Stimma.command' sur le Bureau et lance Stimma."
