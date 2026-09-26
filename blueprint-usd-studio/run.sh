#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/uvicorn ]]; then
  echo "Install the app first: ./omni_setup/setup.sh" >&2
  exit 1
fi
host=127.0.0.1
port=8000
if [[ "${1:-}" == "--lan" ]]; then host=0.0.0.0; shift; fi
if [[ "${1:-}" == "--port" ]]; then port="${2:?port required}"; shift 2; fi
exec .venv/bin/uvicorn app.main:app --host "$host" --port "$port"
