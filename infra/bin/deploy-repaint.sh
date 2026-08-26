#!/bin/sh
set -eu

INFRA_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$INFRA_ROOT/.." && pwd)"
MODAL_BIN="$(command -v modal || echo "modal")"

cd "$REPO_ROOT"
exec "$MODAL_BIN" deploy cloud_repaint/repaint_service.py
