#!/bin/sh
set -eu
ROOT=/Users/mac/adp/comfy
MODAL_PY=/Users/mac/.local/share/uv/tools/modal/bin/modal
cd "$ROOT/stimma"
exec "$MODAL_PY" run cloud_repaint/repaint_service.py::download_models
