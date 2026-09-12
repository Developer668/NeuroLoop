#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON="$ROOT/.runtimes/app/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "NeuroLoop app runtime is not installed." >&2
  exit 1
fi

exec "$PYTHON" "$ROOT/scripts/manage.py" stop
