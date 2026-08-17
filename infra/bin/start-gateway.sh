#!/bin/sh
set -eu

ROOT=/Users/mac/adp/comfy
TOKEN_FILE=/Users/mac/.config/adp-comfy/modal-proxy-token.json
MODAL_PY=/Users/mac/.local/share/uv/tools/modal/bin/python

if [ ! -r "$TOKEN_FILE" ]; then
  echo "Modal proxy token is missing: $TOKEN_FILE" >&2
  exit 1
fi

COMFY_MODAL_URL=$(
  "$MODAL_PY" -c 'import modal; print(modal.Function.from_name("comfyui-minimax-h3", "comfyui").get_web_url())'
)
REPAINT_MODAL_URL=$(
  "$MODAL_PY" -c 'import modal; print(modal.Function.from_name("stimma-flux-fill", "api").get_web_url())' \
  2>/dev/null || true
)
MODAL_PROXY_TOKEN_ID=$(jq -r '."Modal-Key"' "$TOKEN_FILE")
MODAL_PROXY_TOKEN_SECRET=$(jq -r '."Modal-Secret"' "$TOKEN_FILE")
export COMFY_MODAL_URL MODAL_PROXY_TOKEN_ID MODAL_PROXY_TOKEN_SECRET REPAINT_MODAL_URL

mkdir -p "$ROOT/logs"

BRIDGE_PID=""
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
  wait 2>/dev/null || true
  exit 0
}

trap cleanup INT TERM HUP EXIT

start_bridge() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Démarrage modal_bridge.py..."
  "$ROOT/ComfyUI/.venv/bin/python" "$ROOT/modal_bridge.py" \
    >>"$ROOT/logs/modal-bridge.log" 2>&1 &
  BRIDGE_PID=$!
}

start_comfy() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Démarrage ComfyUI local STP (port 8188)..."
  (
    cd "$ROOT/ComfyUI"
    exec .venv/bin/python main.py \
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
start_comfy

while [ "$SHUTDOWN" -eq 0 ]; do
  if [ -z "$BRIDGE_PID" ] || ! kill -0 "$BRIDGE_PID" 2>/dev/null; then
    if [ "$SHUTDOWN" -eq 0 ]; then
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] ATTENTION : modal_bridge.py a crashé ou s'est arrêté. Redémarrage..."
      start_bridge
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

