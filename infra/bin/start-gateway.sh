#!/bin/sh
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOKEN_FILE="${MODAL_PROXY_TOKEN_FILE:-$HOME/.config/adp-comfy/modal-proxy-token.json}"

# Resolve Python environment that has modal installed
MODAL_PY=""
if [ -x "$HOME/.local/share/uv/tools/modal/bin/python" ]; then
  MODAL_PY="$HOME/.local/share/uv/tools/modal/bin/python"
elif [ -x "$ROOT/ComfyUI/.venv/bin/python" ]; then
  MODAL_PY="$ROOT/ComfyUI/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  MODAL_PY="python3"
else
  echo "Python 3 introuvable pour Modal." >&2
  exit 1
fi

if [ ! -r "$TOKEN_FILE" ]; then
  echo "Modal proxy token is missing: $TOKEN_FILE" >&2
  echo "Exécutez 'bin/setup-modal.sh' pour configurer automatiquement votre environnement." >&2
  exit 1
fi

COMFY_MODAL_URL=$(
  "$MODAL_PY" -c 'import modal; print(modal.Function.from_name("comfyui-minimax-h3", "comfyui").get_web_url())'
)
COMFY_MODAL_HD_URL=$(
  "$MODAL_PY" -c 'import modal; print(modal.Function.from_name("comfyui-minimax-h3", "comfyui_hd").get_web_url())' \
  2>/dev/null || true
)
REPAINT_MODAL_URL=$(
  "$MODAL_PY" -c 'import modal; print(modal.Function.from_name("stimma-flux-fill", "api").get_web_url())' \
  2>/dev/null || true
)
TRELLIS2_MODAL_URL=$(
  "$MODAL_PY" -c 'import modal; print(modal.Function.from_name("stimma-trellis2", "api").get_web_url())' \
  2>/dev/null || true
)
MODAL_PROXY_TOKEN_ID=$(jq -r '."Modal-Key"' "$TOKEN_FILE")
MODAL_PROXY_TOKEN_SECRET=$(jq -r '."Modal-Secret"' "$TOKEN_FILE")
export COMFY_MODAL_URL COMFY_MODAL_HD_URL MODAL_PROXY_TOKEN_ID MODAL_PROXY_TOKEN_SECRET REPAINT_MODAL_URL TRELLIS2_MODAL_URL

mkdir -p "$ROOT/logs"

BRIDGE_PID=""
HD_BRIDGE_PID=""
COMFY_PID=""
SHUTDOWN=0

cleanup() {
  SHUTDOWN=1
  echo "\nArrêt de la passerelle et de ses modules..."
  if [ -n "$COMFY_PID" ] && kill -0 "$COMFY_PID" 2>/dev/null; then
    kill "$COMFY_PID" 2>/dev/null || true
  fi
  if [ -n "$BRIDGE_PID" ] && kill -0 "$BRIDGE_PID" 2>/dev/null; then
    kill "$BRIDGE_PID" 2>/dev/null || true
  fi
  if [ -n "$HD_BRIDGE_PID" ] && kill -0 "$HD_BRIDGE_PID" 2>/dev/null; then
    kill "$HD_BRIDGE_PID" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
  exit 0
}

trap cleanup INT TERM HUP EXIT

start_bridge() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Démarrage modal_bridge.py..."
  PYTHON_EXE="$ROOT/ComfyUI/.venv/bin/python"
  if [ ! -x "$PYTHON_EXE" ]; then
    PYTHON_EXE="$MODAL_PY"
  fi
  "$PYTHON_EXE" "$ROOT/modal_bridge.py" \
    >>"$ROOT/logs/modal-bridge.log" 2>&1 &
  BRIDGE_PID=$!
}

start_hd_bridge() {
  if [ -z "$COMFY_MODAL_HD_URL" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Route HD B300 indisponible : déployez la fonction comfyui_hd." >&2
    return
  fi
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Démarrage du proxy HD B300 (port 8191)..."
  PYTHON_EXE="$ROOT/ComfyUI/.venv/bin/python"
  if [ ! -x "$PYTHON_EXE" ]; then
    PYTHON_EXE="$MODAL_PY"
  fi
  (
    COMFY_MODAL_URL="$COMFY_MODAL_HD_URL" MODAL_BRIDGE_PORT=8191 \
      "$PYTHON_EXE" "$ROOT/modal_bridge.py" \
      >>"$ROOT/logs/modal-bridge-hd.log" 2>&1
  ) &
  HD_BRIDGE_PID=$!
}

start_comfy() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Démarrage ComfyUI local STP (port 8188)..."
  PYTHON_EXE="$ROOT/ComfyUI/.venv/bin/python"
  if [ ! -x "$PYTHON_EXE" ]; then
    PYTHON_EXE="$MODAL_PY"
  fi
  (
    cd "$ROOT/ComfyUI"
    exec "$PYTHON_EXE" main.py \
      --cpu \
      --listen 127.0.0.1 \
      --port 8188 \
      --disable-auto-launch \
      --preview-method none >>"$ROOT/logs/comfyui.log" 2>&1
  ) &
  COMFY_PID=$!
}

echo "=== Superviseur Passerelle Modal H3 (Auto-Restart Actif) ==="
echo "Passerelle locale prête sur http://127.0.0.1:8188"
if [ -n "$REPAINT_MODAL_URL" ]; then
  echo "Route Repaint Modal active via /repaint (GPU NVIDIA L40S 48 GB)."
else
  echo "Route Repaint Modal indisponible : déployez stimma/cloud_repaint/repaint_service.py." >&2
fi
echo "Ctrl-C arrête proprement la passerelle locale; le GPU Modal scale à zéro automatiquement."

start_bridge
start_hd_bridge
start_comfy

while [ "$SHUTDOWN" -eq 0 ]; do
  if [ -z "$BRIDGE_PID" ] || ! kill -0 "$BRIDGE_PID" 2>/dev/null; then
    if [ "$SHUTDOWN" -eq 0 ]; then
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] ATTENTION : modal_bridge.py a crashé ou s'est arrêté. Redémarrage..."
      start_bridge
    fi
  fi

  if [ -n "$COMFY_MODAL_HD_URL" ] && { [ -z "$HD_BRIDGE_PID" ] || ! kill -0 "$HD_BRIDGE_PID" 2>/dev/null; }; then
    if [ "$SHUTDOWN" -eq 0 ]; then
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] ATTENTION : proxy HD B300 arrêté. Redémarrage..."
      start_hd_bridge
    fi
  fi

  if [ -z "$COMFY_PID" ] || ! kill -0 "$COMFY_PID" 2>/dev/null; then
    if [ "$SHUTDOWN" -eq 0 ]; then
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] ATTENTION : ComfyUI STP a crashé ou s'est arrêté. Redémarrage..."
      start_comfy
    fi
  fi

  sleep 2
done
