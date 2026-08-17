#!/bin/sh
set -eu

cd /Users/mac/adp/comfy
modal run modal_h3.py::download_models
modal run modal_h3.py::download_music_models
