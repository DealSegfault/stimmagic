#!/bin/sh
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$ROOT/bin:$PATH"
cd "$ROOT/stimma"

stimma_target=$(rustc -vV | awk '/^host:/ {print $2}')
stimma_watchdog="src-tauri/binaries/stimma-watchdog-$stimma_target"
stimma_backend="src-tauri/binaries/stimma-backend-$stimma_target"

if [ ! -x "$stimma_watchdog" ]; then
  ./src-tauri/build-watchdog.sh
fi

# The production PyInstaller sidecar is not used in dev mode, but Tauri still
# validates that the configured resource exists before compiling the shell.
if [ ! -x "$stimma_backend" ]; then
  cp "$ROOT/bin/stimma-backend-dev-placeholder" "$stimma_backend"
  chmod 755 "$stimma_backend"
fi

exec ./tools/stimma dev all
