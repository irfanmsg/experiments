#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
mode="${1:-core}"
case "$mode" in
  core|runtime) ;;
  *) printf 'Usage: %s [core|runtime]\n' "$0" >&2; exit 2 ;;
esac

if ! command -v uv >/dev/null 2>&1; then
  echo 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/' >&2
  exit 1
fi
sync_args=()
if [[ "$mode" == runtime ]]; then sync_args+=(--extra runtime); fi
# Retain an installed runtime when somebody reruns core setup.
uv sync --locked --inexact --python "${BLUEPRINT_STUDIO_PYTHON:-python3}" "${sync_args[@]}"
venv_dir="${UV_PROJECT_ENVIRONMENT:-$repo_dir/.venv}"
venv_python="$venv_dir/bin/python"

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

printf 'Ready: %s\n' "$venv_dir"
