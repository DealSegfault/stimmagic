#!/bin/sh
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
modal run modal_h3.py::download_models
modal run modal_h3.py::download_music_models
