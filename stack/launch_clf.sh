#!/usr/bin/env bash
# airlock-clf :8002 — NOT PART OF THE COMMITTED DEMO CONFIG.
# Owner: A. ONLY A runs this (NFR-S1). Run stack/preflight.sh FIRST.
#
# Under the pre-staged weights (stack/models.env) T2 runs on :8000 — the only
# classifier weights on disk are a second copy of Lightning (21 GB), which at
# any honest utilisation pushes the sum past the 0.85 ceiling (NFR-S3).
# Launch this ONLY if A's measurement shows the 30B missing NFR-L3
# (p95 <= 600 ms) AND the budget has been re-cut on the whiteboard first.
set -euo pipefail

# stack/models.env maps the pre-staged weights onto the model roles —
# source it so the PATH (launch) / NAME (request) split cannot be mixed up.
if [ -f "$(dirname "$0")/models.env" ]; then
  set -a; . "$(dirname "$0")/models.env"; set +a
fi

MODEL="${AIRLOCK_CLF_MODEL_PATH:?set AIRLOCK_CLF_MODEL_PATH — but read the header first: under the pre-staged weights the demo config is TWO servers and T2 runs on :8000}"
IMAGE="${AIRLOCK_CLF_IMAGE:-vllm/vllm-openai:latest}"
UTIL="${AIRLOCK_CLF_UTIL:?REFUSING: two-server config is committed (T2 on :8000).
Set AIRLOCK_CLF_UTIL explicitly (whiteboard re-cut first, sum <= 0.85) to override}"

bash "$(dirname "$0")/preflight.sh"

docker run -d --name airlock-clf --gpus all \
  -p 127.0.0.1:8002:8002 \
  -v "${AIRLOCK_MODELS_DIR:-/mnt/data/models}:/models:ro" \
  -e VLLM_MARLIN_USE_ATOMIC_ADD=1 \
  -e VLLM_USE_FLASHINFER_MOE_FP4=0 \
  -e CUTE_DSL_ARCH=sm_121a \
  "$IMAGE" \
  --model "$MODEL" \
  --served-model-name airlock-clf \
  --host 0.0.0.0 --port 8002 \
  --gpu-memory-utilization "$UTIL" \
  --max-model-len 8192 \
  --max-num-seqs 8 \
  --limit-mm-per-prompt '{"image":0,"video":0}'

echo "airlock-clf launching at $UTIL. UPDATE THE WHITEBOARD — sum must stay <= 0.85."
echo "Prefix caching serves the byte-identical T2 system prompt; keep it ON."
