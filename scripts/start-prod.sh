#!/usr/bin/env sh
# Run from repo root: Python ECM backend (Waitress) + Node gateway (static + /api + /ecm proxy).
set -e
cd "$(dirname "$0")/.."

export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"

if ! command -v waitress-serve >/dev/null 2>&1; then
  echo "waitress-serve not found. Install Python deps: pip install -r requirements.txt" >&2
  exit 1
fi

waitress-serve --listen=127.0.0.1:9000 app.main:app &
BACK_PID=$!
trap 'kill "$BACK_PID" 2>/dev/null; exit' INT TERM EXIT

exec node server/prod.js
