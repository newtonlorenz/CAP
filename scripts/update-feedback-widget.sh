#!/usr/bin/env bash
set -euo pipefail
source_repo="${1:?Pass the path to the independent page-feedback repository}"
cap_root="$(cd "$(dirname "$0")/.." && pwd)"
source_repo="$(cd "$source_repo" && pwd)"
test -f "$source_repo/widget/package.json"
package_dir="$(mktemp -d)"
trap 'rm -rf "$package_dir"' EXIT
cd "$source_repo/widget"
npm ci --ignore-scripts
npm pack --pack-destination "$package_dir"
mkdir -p "$cap_root/frontend/vendor"
cp "$package_dir"/*.tgz "$cap_root/frontend/vendor/"
package_name="$(basename "$package_dir"/*.tgz)"
cd "$cap_root/frontend"
npm install "./vendor/$package_name" --ignore-scripts
npm run build
