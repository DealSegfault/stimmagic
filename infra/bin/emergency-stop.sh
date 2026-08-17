#!/bin/sh
set -eu

modal app stop comfyui-minimax-h3 --yes
echo "App Modal arrêtée. Relancer bin/deploy.sh avant la prochaine session."
