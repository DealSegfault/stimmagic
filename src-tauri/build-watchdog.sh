#!/bin/bash
# Build the stimma-watchdog binary for the current platform

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WATCHDOG_DIR="$SCRIPT_DIR/watchdog"
BINARIES_DIR="$SCRIPT_DIR/binaries"

# Get target triple
TARGET=$(rustc -vV | grep host | cut -d' ' -f2)
case "$TARGET" in
  *-windows-msvc) EXE_SUFFIX=".exe" ;;
  *) EXE_SUFFIX="" ;;
esac

echo "Building stimma-watchdog for $TARGET..."

# Build release binary
cd "$WATCHDOG_DIR"
cargo build --release

# Copy to binaries directory with target triple suffix
mkdir -p "$BINARIES_DIR"
cp "$WATCHDOG_DIR/target/release/stimma-watchdog$EXE_SUFFIX" "$BINARIES_DIR/stimma-watchdog-$TARGET$EXE_SUFFIX"

echo "Built: $BINARIES_DIR/stimma-watchdog-$TARGET$EXE_SUFFIX"
ls -la "$BINARIES_DIR/stimma-watchdog-$TARGET$EXE_SUFFIX"
