#!/usr/bin/env bash
# Development preview only; not the final redistributable GNOME desktop package.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
for required in ".venv/bin/python" ".tools/node/bin/node" ".tools/npm/bin/npm-cli.js" "apps/desktop/node_modules/electron/dist/electron"; do
  if [[ ! -e "$required" ]]; then
    echo "URDFTools missing local development dependency: $required" >&2
    echo "Run the documented S01 local toolchain installer first." >&2
    exit 2
  fi
done
export PATH="$ROOT/.tools/node/bin:$PATH"
"$ROOT/.tools/node/bin/node" "$ROOT/.tools/npm/bin/npm-cli.js" run build
exec "$ROOT/apps/desktop/node_modules/electron/dist/electron" "$ROOT/apps/desktop" "$@"
