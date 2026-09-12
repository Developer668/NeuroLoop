#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON="$ROOT/.runtimes/app/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "NeuroLoop is not set up yet. Create .runtimes/app with the pinned setup first." >&2
  exit 1
fi

if [ ! -f "$ROOT/.env" ]; then
  umask 077
  "$PYTHON" -c 'from pathlib import Path; import secrets, sys; p=Path(sys.argv[1]); p.write_text("NEUROLOOP_AUTH_TOKEN=" + secrets.token_urlsafe(32) + "\n", encoding="utf-8"); p.chmod(0o600)' "$ROOT/.env"
fi

case "$(uname -s)" in
  Darwin)
    export NEUROLOOP_INFERENCE_DEVICE="${NEUROLOOP_INFERENCE_DEVICE:-mps}"
    export NEUROLOOP_ALLOW_MPS_INFERENCE="${NEUROLOOP_ALLOW_MPS_INFERENCE:-true}"
    export NEUROLOOP_MPS_MEMORY_RESERVE_GIB="${NEUROLOOP_MPS_MEMORY_RESERVE_GIB:-1.5}"
    export PYTORCH_ENABLE_MPS_FALLBACK="${PYTORCH_ENABLE_MPS_FALLBACK:-1}"
    ;;
esac

exec "$PYTHON" "$ROOT/scripts/manage.py" serve "$@"
