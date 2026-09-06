#!/bin/sh
set -eu

INFRA_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -n "${STIMMA_LAUNCH_LOG_DIR:-}" ]; then
  LOG_ROOT="$STIMMA_LAUNCH_LOG_DIR"
elif [ -n "${LOCALAPPDATA:-}" ] && command -v cygpath >/dev/null 2>&1; then
  LOG_ROOT="$(cygpath -u "$LOCALAPPDATA")/Stimma/Logs"
else
  LOG_ROOT="$HOME/Library/Logs/Stimma"
fi
BACKEND_URL="${STIMMA_BACKEND_URL:-http://127.0.0.1:9191}"
WAIT_SECONDS="${STIMMA_LAUNCH_TIMEOUT_SECONDS:-900}"

# Finder-launched .command files do not always inherit the user's interactive
# shell PATH. Include the conventional install locations used by Homebrew,
# Rust, uv, Deno, and Codex before starting the checked-out development app.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$HOME/.deno/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
# The local bridge reads a restricted wk-/ws- Proxy Token from its protected
# config file. Account-level setup credentials must not remain in long-running
# gateway or app processes.
unset MODAL_TOKEN_ID MODAL_TOKEN_SECRET HF_TOKEN 2>/dev/null || true

case "$WAIT_SECONDS" in
  ''|*[!0-9]*)
    echo "STIMMA_LAUNCH_TIMEOUT_SECONDS doit être un nombre entier." >&2
    exit 1
    ;;
esac

if [ -x "$INFRA_ROOT/.runtime/ComfyUI/.venv/bin/python" ]; then
  PYTHON_EXE="$INFRA_ROOT/.runtime/ComfyUI/.venv/bin/python"
elif [ -x "$INFRA_ROOT/.runtime/ComfyUI/.venv/Scripts/python.exe" ]; then
  PYTHON_EXE="$INFRA_ROOT/.runtime/ComfyUI/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_EXE="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_EXE="$(command -v python)"
else
  echo "Python 3 est requis pour lancer et vérifier Stimma." >&2
  exit 1
fi

mkdir -p "$LOG_ROOT"

port_is_open() {
  "$PYTHON_EXE" - "$1" <<'PY'
import socket
import sys

with socket.socket() as sock:
    sock.settimeout(0.3)
    raise SystemExit(sock.connect_ex(("127.0.0.1", int(sys.argv[1]))) != 0)
PY
}

start_gateway_if_needed() {
  if port_is_open 8188 && port_is_open 8190; then
    echo "Passerelle Modal déjà active."
    return
  fi
  if port_is_open 8188 || port_is_open 8190; then
    echo "Démarrage refusé : les ports 8188/8190 sont partiellement occupés." >&2
    echo "Fermez l'ancien processus puis relancez ce raccourci." >&2
    exit 1
  fi

  echo "Démarrage de la passerelle Modal..."
  nohup "$INFRA_ROOT/bin/start-gateway.sh" >>"$LOG_ROOT/gateway.log" 2>&1 &
  echo "$!" >"$LOG_ROOT/gateway.pid"
}

start_stimma_if_needed() {
  if port_is_open 9191 && port_is_open 9192; then
    echo "Stimma est déjà lancé."
    return
  fi
  if port_is_open 9191 || port_is_open 9192; then
    echo "Démarrage refusé : les ports 9191/9192 sont partiellement occupés." >&2
    echo "Fermez l'ancien processus puis relancez ce raccourci." >&2
    exit 1
  fi

  echo "Démarrage de Stimma..."
  nohup "$INFRA_ROOT/bin/start-stimma.sh" >>"$LOG_ROOT/stimma.log" 2>&1 &
  echo "$!" >"$LOG_ROOT/stimma.pid"
}

ready_for_first_video() {
  "$PYTHON_EXE" - "$BACKEND_URL" <<'PY'
import json
import sys
from urllib.parse import urlencode
from urllib.request import urlopen

base_url = sys.argv[1].rstrip("/")


def get_json(path: str):
    with urlopen(base_url + path, timeout=3) as response:
        return json.load(response)


try:
    profiles = get_json("/api/profiles").get("profiles", [])
    if not profiles or not profiles[0].get("id"):
        raise RuntimeError("aucun profil Stimma disponible")
    profile_id = profiles[0]["id"]
    profile_query = urlencode({"profile": profile_id})

    settings = get_json(f"/api/settings?{profile_query}")
    readiness = settings.get("readiness")
    if readiness is not None and not readiness.get("has_agent_llm"):
        raise RuntimeError("Codex CLI n'est pas disponible comme agent LLM")

    gateway = get_json(f"/api/gateway/status?{profile_query}")
    if not gateway.get("running"):
        raise RuntimeError("la passerelle Modal n'est pas prête")

    query = urlencode({
        "provider_id": "comfyui-modal-h3",
        "include_unavailable": "false",
        "profile": profile_id,
    })
    tools = get_json(f"/api/tools/providers/tools?{query}")
    if not any(
        tool.get("availability") == "available"
        and str(tool.get("tool_id", "")).startswith("minimax-h3-")
        for tool in tools
    ):
        raise RuntimeError("aucun outil vidéo MiniMax H3 n'est disponible")
except (OSError, ValueError, RuntimeError):
    raise SystemExit(1)
PY
}

start_gateway_if_needed
start_stimma_if_needed

echo "Vérification de Codex, de la passerelle et des outils vidéo H3..."
deadline=$(($(date +%s) + WAIT_SECONDS))
while ! ready_for_first_video; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "Stimma n'est pas devenu prêt dans le délai imparti." >&2
    echo "Logs : $LOG_ROOT/gateway.log" >&2
    echo "       $LOG_ROOT/stimma.log" >&2
    exit 1
  fi
  sleep 5
done

echo "Stimma est lancé et prêt à générer votre première vidéo."
if command -v osascript >/dev/null 2>&1; then
  osascript -e 'display notification "Stimma est lancé et prêt à générer votre première vidéo." with title "Stimma"' >/dev/null 2>&1 || true
fi
