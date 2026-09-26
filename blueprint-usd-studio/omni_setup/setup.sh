#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mode="${1:-core}"
case "$mode" in
  core|runtime) ;;
  *) printf 'Usage: %s [core|runtime]\n' "$0" >&2; exit 2 ;;
esac

python_bin="${BLUEPRINT_STUDIO_PYTHON:-python3}"
"$python_bin" -c 'import sys; assert (3, 10) <= sys.version_info[:2] < (3, 14), "Python 3.10–3.13 required"'

if [[ ! -x "$repo_dir/.venv/bin/python" ]] || ! "$repo_dir/.venv/bin/python" -m pip --version >/dev/null 2>&1; then
  "$python_bin" -m venv "$repo_dir/.venv"
fi
venv_python="$repo_dir/.venv/bin/python"
"$venv_python" -m pip install --upgrade pip
"$venv_python" -m pip install -r "$repo_dir/omni_setup/requirements-core.txt"

if [[ "$mode" == runtime ]]; then
  "$venv_python" -m pip install -r "$repo_dir/omni_setup/requirements-runtime.txt"
fi

"$venv_python" - <<'PY'
from pxr import Usd, UsdGeom, UsdShade, UsdPhysics
import usdex.core
print("OpenUSD authoring imports passed")
PY

if [[ "$mode" == runtime ]]; then
  "$venv_python" - <<'PY'
import ovstage, ovrtx, ovstream, ovphysx
print("Omniverse runtime imports passed")
PY
fi

printf 'Ready: %s/.venv\n' "$repo_dir"
