#!/bin/sh
set -eu

INFRA_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$INFRA_ROOT/.." && pwd)"
RUNTIME_ROOT="${STIMMA_RUNTIME_DIR:-$INFRA_ROOT/.runtime}"
TOKEN_FILE="${MODAL_PROXY_TOKEN_FILE:-$HOME/.config/adp-comfy/modal-proxy-token.json}"
export PATH="$INFRA_ROOT/bin:$PATH"
export STIMMA_MODAL_GATEWAY_URL="${STIMMA_MODAL_GATEWAY_URL:-ws://127.0.0.1:8188/stp-v1}"
cd "$REPO_ROOT"

# TRELLIS.2 is called directly by the Stimma backend rather than through the
# ComfyUI bridge, so resolve its Modal URL and proxy credentials in this
# process as well. Missing Modal setup simply leaves the 3D feature disabled.
MODAL_PY=""
if [ -x "$HOME/.local/share/uv/tools/modal/bin/python" ]; then
  MODAL_PY="$HOME/.local/share/uv/tools/modal/bin/python"
elif [ -x "$RUNTIME_ROOT/ComfyUI/.venv/bin/python" ]; then
  MODAL_PY="$RUNTIME_ROOT/ComfyUI/.venv/bin/python"
elif [ -x "$RUNTIME_ROOT/ComfyUI/.venv/Scripts/python.exe" ]; then
  MODAL_PY="$RUNTIME_ROOT/ComfyUI/.venv/Scripts/python.exe"
fi
if [ -n "$MODAL_PY" ] && [ -r "$TOKEN_FILE" ]; then
  TRELLIS2_MODAL_URL="${TRELLIS2_MODAL_URL:-$(
    "$MODAL_PY" -c 'import modal; print(modal.Function.from_name("stimma-trellis2", "api").get_web_url())' \
      2>/dev/null || true
  )}"
  MODAL_PROXY_TOKEN_ID="${MODAL_PROXY_TOKEN_ID:-$(
    "$MODAL_PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["Modal-Key"])' "$TOKEN_FILE"
  )}"
  MODAL_PROXY_TOKEN_SECRET="${MODAL_PROXY_TOKEN_SECRET:-$(
    "$MODAL_PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["Modal-Secret"])' "$TOKEN_FILE"
  )}"
  export TRELLIS2_MODAL_URL MODAL_PROXY_TOKEN_ID MODAL_PROXY_TOKEN_SECRET
fi

stimma_target=$(rustc -vV | awk '/^host:/ {print $2}')
case "$stimma_target" in
  *-windows-msvc) stimma_exe_suffix=".exe" ;;
  *) stimma_exe_suffix="" ;;
esac
stimma_watchdog="src-tauri/binaries/stimma-watchdog-$stimma_target$stimma_exe_suffix"
stimma_backend="src-tauri/binaries/stimma-backend-$stimma_target"

if [ ! -x "$stimma_watchdog" ]; then
  ./src-tauri/build-watchdog.sh
fi

# The production PyInstaller sidecar is not used in dev mode, but Tauri still
# validates that the configured resource exists before compiling the shell.
if [ ! -x "$stimma_backend" ]; then
  cp "$INFRA_ROOT/bin/stimma-backend-dev-placeholder" "$stimma_backend"
  chmod 755 "$stimma_backend"
fi

exec ./tools/stimma dev all
