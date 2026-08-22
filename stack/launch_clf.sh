#!/usr/bin/env bash
# airlock-clf :8002 — Qwen3-4B-Instruct-2507 BF16 at --gpu-memory-utilization 0.09.
# Owner: A. ONLY A runs this (NFR-S1). Run stack/preflight.sh FIRST.
#
# Fallback (SRS §3): if this won't fit or boot, do NOT fight it — set
# AIRLOCK_CLF_URL=http://127.0.0.1:8000/v1 on the inspect service and route T2
# to the 35B. Costs latency, costs no memory.
set -euo pipefail

MODEL="${AIRLOCK_CLF_MODEL:-Qwen/Qwen3-4B-Instruct-2507}"
IMAGE="${AIRLOCK_CLF_IMAGE:-vllm/vllm-openai:latest}"

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
  --gpu-memory-utilization 0.09 \
  --max-model-len 8192 \
  --max-num-seqs 8 \
  --limit-mm-per-prompt '{"image":0,"video":0}'

echo "airlock-clf launching. Whiteboard: +0.09 (total 0.73 with text+vision — ceiling 0.85)."
echo "Prefix caching serves the byte-identical T2 system prompt; keep it ON."
