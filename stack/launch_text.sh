#!/usr/bin/env bash
# airlock-text :8000 — Qwen3.6-35B-A3B-NVFP4 at --gpu-memory-utilization 0.40.
# Owner: A. ONLY A runs this (NFR-S1). Run stack/preflight.sh FIRST (NFR-S2)
# and write the new whiteboard total BEFORE this command (NFR-S3).
#
# Flags are verbatim from SRS §10 Phase 0 item 4 / §7.5:
#   0.40 util ≈ 51.6 GB of the shared 128 GB pool (w ~22 + FP8 KV ~26 + graphs ~3)
#   --moe-backend marlin  MANDATORY on NVFP4 MoE — emits garbage on sm121 otherwise
#   --max-num-seqs 8      NFR-S7: above ~4 decode streams TTFT spikes
#   MTP spec-decode stays ON here and ONLY here (§7.1 — vision emits ≤8 tokens)
set -euo pipefail

MODEL="${AIRLOCK_TEXT_MODEL:?set AIRLOCK_TEXT_MODEL to the pre-staged weights path (VERIFY-ON-THE-DAY: exact snapshot dir on the box)}"
IMAGE="${AIRLOCK_TEXT_IMAGE:-vllm/vllm-openai:latest}"

bash "$(dirname "$0")/preflight.sh"

docker run -d --name airlock-text --gpus all \
  -p 127.0.0.1:8000:8000 \
  -v "${AIRLOCK_MODELS_DIR:-/mnt/data/models}:/models:ro" \
  -e VLLM_MARLIN_USE_ATOMIC_ADD=1 \
  -e VLLM_USE_FLASHINFER_MOE_FP4=0 \
  -e CUTE_DSL_ARCH=sm_121a \
  "$IMAGE" \
  --model "$MODEL" \
  --served-model-name airlock-text \
  --host 0.0.0.0 --port 8000 \
  --gpu-memory-utilization 0.40 \
  --max-model-len 32768 \
  --max-num-seqs 8 \
  --moe-backend marlin \
  --kv-cache-dtype fp8 \
  --limit-mm-per-prompt '{"image":0,"video":0}' \
  --speculative-config '{"method":"mtp","num_speculative_tokens":3}'

echo "airlock-text launching. Whiteboard: +0.40. First compile 25-57 s — NOT a hang."
echo "Next: stack/warm.sh once /health returns 200."
