#!/usr/bin/env bash
# stack/run_inspect.sh — start the inspect service with models.env sourced.
#
# RUN-DAY §2 calls the env "load-bearing" and it is: t2.py defaults to :8002, a server
# the committed two-server config never launches. Start uvicorn without models.env and
# every paste that escalates hits a dead port, fail-closes to BLOCK, and the FPR comes
# back near-total looking exactly like a broken detector. A script removes the chance of
# forgetting it in a fresh terminal.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . stack/models.env; set +a
echo "CLF_URL=$AIRLOCK_CLF_URL"
[ "$AIRLOCK_CLF_URL" = "http://127.0.0.1:8000/v1" ] || { echo "REFUSING: CLF_URL is not :8000/v1"; exit 1; }
exec .venv/bin/uvicorn services.inspect.app:app --host 127.0.0.1 --port "${PORT:-8787}" "$@"
