#!/bin/sh
set -eu

export PATH="/Users/mac/adp/comfy/bin:$PATH"
cd /Users/mac/adp/comfy/stimma

stimma_target=$(rustc -vV | awk '/^host:/ {print $2}')
stimma_watchdog="src-tauri/binaries/stimma-watchdog-$stimma_target"
stimma_backend="src-tauri/binaries/stimma-backend-$stimma_target"

if [ ! -x "$stimma_watchdog" ]; then
  ./src-tauri/build-watchdog.sh
fi

# The production PyInstaller sidecar is not used in dev mode, but Tauri still
# validates that the configured resource exists before compiling the shell.
if [ ! -x "$stimma_backend" ]; then
  cp /Users/mac/adp/comfy/bin/stimma-backend-dev-placeholder "$stimma_backend"
  chmod 755 "$stimma_backend"
fi

exec ./tools/stimma dev all
