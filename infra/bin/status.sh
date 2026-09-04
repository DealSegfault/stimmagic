#!/bin/sh
set -eu

APP_ID=$(modal app list --json | jq -r '[.[] | select(.state == "deployed")][0].app_id // empty')
if [ -n "$APP_ID" ]; then
  echo "App déployée: $APP_ID"
  modal container list --app-id "$APP_ID"
else
  echo "Aucune app Modal actuellement déployée"
fi

modal billing report --for today --show-resources --json | jq -r '
  . as $all
  | ($all | map(select(.cost != null))) as $rows
  | ($rows | group_by(.resource)[]
      | "\(.[0].resource): $\((map((.cost // 0) | tonumber) | add) * 100000 | round / 100000)") ,
    "Total workspace Modal aujourd’hui: $\((($rows | map((.cost // 0) | tonumber) | add // 0) * 100000) | round / 100000)"
'
