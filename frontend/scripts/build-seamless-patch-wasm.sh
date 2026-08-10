#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
frontend_dir="$(cd -- "$script_dir/.." && pwd)"
crate_dir="$frontend_dir/src/imageEditor/stack/seamless-patch-wasm"
output_dir="$frontend_dir/src/imageEditor/stack/seamlessPatchWasm"

wasm-pack build "$crate_dir" \
  --target web \
  --release \
  --no-typescript \
  --out-dir "$output_dir" \
  --out-name seamlessPatchWasm

# The module is bundled directly by Vite rather than published as an npm
# package. Keep only the reproducible runtime artifacts in the source tree.
rm -f "$output_dir/.gitignore" "$output_dir/package.json"
