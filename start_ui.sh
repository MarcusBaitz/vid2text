#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

HOST_NAME="${VID2TEXT_UI_HOST:-127.0.0.1}"
PORT="${VID2TEXT_UI_PORT:-7860}"
NO_BROWSER=0
SKIP_INSTALL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST_NAME="${2:-}"
      [[ -n "$HOST_NAME" ]] || { echo "--host braucht einen Wert." >&2; exit 1; }
      shift 2
      ;;
    --port)
      PORT="${2:-}"
      [[ -n "$PORT" ]] || { echo "--port braucht einen Wert." >&2; exit 1; }
      shift 2
      ;;
    --no-browser)
      NO_BROWSER=1
      shift
      ;;
    --skip-install)
      SKIP_INSTALL=1
      shift
      ;;
    *)
      echo "Unbekannte Option: $1" >&2
      exit 1
      ;;
  esac
done

RUN_ARGS=(--diagnose)
[[ "$SKIP_INSTALL" -eq 1 ]] && RUN_ARGS+=(--skip-install)

printf '\n==> Runtime wird vorbereitet\n' >&2
bash "$ROOT/run.sh" "${RUN_ARGS[@]}"

PYTHON_EXE="$ROOT/.venv/bin/python"
[[ -x "$PYTHON_EXE" ]] || { echo "Python in .venv wurde nicht gefunden: $PYTHON_EXE" >&2; exit 1; }

UI_ARGS=("$ROOT/web_app.py" --host "$HOST_NAME" --port "$PORT")
[[ "$NO_BROWSER" -eq 1 ]] && UI_ARGS+=(--no-browser)

printf '\n==> UI startet auf http://%s:%s\n' "$HOST_NAME" "$PORT" >&2
exec "$PYTHON_EXE" "${UI_ARGS[@]}"
