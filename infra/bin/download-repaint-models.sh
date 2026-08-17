#!/bin/sh
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODAL_BIN="$(command -v modal || echo "modal")"

cd "$ROOT/stimma"
exec "$MODAL_BIN" run cloud_repaint/repaint_service.py::download_models
