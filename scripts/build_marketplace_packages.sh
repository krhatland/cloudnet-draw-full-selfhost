#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist/marketplace"
BUILD_DIR="$ROOT_DIR/.build/marketplace"

rm -rf "$DIST_DIR" "$BUILD_DIR"
mkdir -p "$DIST_DIR" "$BUILD_DIR"

FUNCTION_ZIP="$BUILD_DIR/function.zip"

(
  cd "$ROOT_DIR/function"
  zip -qr "$FUNCTION_ZIP" .
)

build_package() {
  local variant="$1"
  local package_dir="$BUILD_DIR/$variant"

  mkdir -p "$package_dir/artifacts"
  cp "$ROOT_DIR/infra/mainTemplate.json" "$package_dir/mainTemplate.json"
  cp "$ROOT_DIR/marketplace/$variant/createUiDefinition.json" "$package_dir/createUiDefinition.json"
  cp "$FUNCTION_ZIP" "$package_dir/artifacts/function.zip"

  (
    cd "$package_dir"
    zip -qr "$DIST_DIR/$variant.zip" .
  )
}

build_package "storage-only"
build_package "confluence-export"

cp "$FUNCTION_ZIP" "$ROOT_DIR/artifacts/function.zip"

echo "Created packages:"
echo "  $DIST_DIR/storage-only.zip"
echo "  $DIST_DIR/confluence-export.zip"
