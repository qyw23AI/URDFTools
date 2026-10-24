#!/usr/bin/env bash
# Writable portable-directory launcher. Never touches system Python, Codex, or user shell rc.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
for env_dir in ".venv" ".tools/cad-venv" ".tools/model-venv" ".tools/results-venv" ".tools/sim-venv"; do
  venv="$ROOT/$env_dir"
  [[ -d "$venv/bin" ]] || { echo "Missing bundled environment: $env_dir" >&2; exit 2; }
  for name in python python3 python3.12; do
    ln -sfn "$ROOT/.tools/python/bin/python3.12" "$venv/bin/$name"
  done
  cat > "$venv/pyvenv.cfg" <<EOF
home = $ROOT/.tools/python/bin
include-system-site-packages = false
version = 3.12.14
executable = $ROOT/.tools/python/bin/python3.12
EOF
done
unset PYTHONHOME PYTHONPATH PYTHONSTARTUP NODE_OPTIONS ELECTRON_RUN_AS_NODE
export PYTHONNOUSERSITE=1
if [[ "${1-}" == "--check" ]]; then
  export URDFTOOLS_PORTABLE_ROOT="$ROOT"
  exec "$ROOT/.venv/bin/python" -c 'import json,os,sys; print(json.dumps({"base_prefix":sys.base_prefix,"prefix":sys.prefix,"root":os.environ["URDFTOOLS_PORTABLE_ROOT"],"python":sys.version.split()[0]}))'
fi
if [[ "${1-}" == "--cli" ]]; then
  shift
  export PYTHONPATH="$ROOT/python"
  exec "$ROOT/.venv/bin/python" -m urdftools "$@"
fi
exec "$ROOT/apps/desktop/node_modules/electron/dist/electron" "$ROOT/apps/desktop" "$@"
