#!/bin/sh
set -eu

for app_name in comfyui-minimax-h3 stimma-flux-fill maya-latentsync stimma-trellis2; do
  modal app stop "$app_name" --yes 2>/dev/null || true
done
echo "Applications Modal arrêtées. Relancez le setup ou le déploiement voulu avant la prochaine session."
