#!/bin/sh
set -eu

APP_ID=$(modal app list --json | jq -r '[.[] | select(.description == "comfyui-minimax-h3" and .state == "deployed")][0].app_id // empty')
if [ -z "$APP_ID" ]; then
  echo "comfyui-minimax-h3 n'est pas déployé"
  exit 0
fi

echo "App: $APP_ID"
modal container list --app-id "$APP_ID"
modal billing report --for today --show-resources --json | jq -r '
  [.[] | select(.description == "comfyui-minimax-h3")] as $rows
  | ($rows | group_by(.resource)[]
      | "\(.[0].resource): $\((map(.cost | tonumber) | add) * 100000 | round / 100000)") ,
    "Total ComfyUI H3 aujourd’hui: $\((($rows | map(.cost | tonumber) | add // 0) * 100000) | round / 100000)"
'
