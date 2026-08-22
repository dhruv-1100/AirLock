#!/usr/bin/env bash
# airlock-text :8000 — Qwen3.6-35B-A3B-NVFP4 at --gpu-memory-utilization 0.40.
# Owner: A. ONLY A runs this (NFR-S1). Run stack/preflight.sh FIRST (NFR-S2)
# and write the new whiteboard total BEFORE this command (NFR-S3).
#
# Flags are verbatim from SRS §10 Phase 0 item 4 / §7.5:
#   0.40 util ≈ 51.6 GB of the shared pool — holds for the pre-staged
#   Nemotron Lightning 30B NVFP4 too (w ~21 + FP8 KV ~26 + graphs ~3)
#   --moe-backend marlin  MANDATORY on NVFP4 MoE — emits garbage on sm121 otherwise
#   --max-num-seqs 8      NFR-S7: above ~4 decode streams TTFT spikes
#   MTP spec-decode stays ON here and ONLY here (§7.1 — vision emits ≤8 tokens)
set -euo pipefail

# stack/models.env maps the pre-staged weights onto the model roles —
# source it so the PATH (launch) / NAME (request) split cannot be mixed up.
if [ -f "$(dirname "$0")/models.env" ]; then
  set -a; . "$(dirname "$0")/models.env"; set +a
fi

MODEL="${AIRLOCK_TEXT_MODEL_PATH:?set AIRLOCK_TEXT_MODEL_PATH (weights path, e.g. /models/lightning) — NOT AIRLOCK_TEXT_MODEL, which is the request name}"
IMAGE="${AIRLOCK_TEXT_IMAGE:-vllm/vllm-openai:latest}"

# Entrypoint shim. vllm/vllm-openai has ENTRYPOINT ["vllm","serve"], so bare flags work.
# nvcr.io/nvidia/vllm runs nvidia_entrypoint.sh, which execs its Cmd verbatim — bare
# flags give `exec: --: invalid option` and the container exits(2) in under a second.
# Empty default preserves the original behaviour exactly; models.env sets it when the
# NVIDIA image is in use. Also carries --trust-remote-code, which the Nemotron custom
# architectures require (the working af-vllm container passed it).
# MTP spec-decode and prefix caching are mutually exclusive on this vLLM build: with
# --speculative-config set, the engine reports enable_prefix_caching=False. §7.1 says
# "Prefix caching stays ON" because the T2 system prompt plus six few-shot exemplars are
# byte-identical on every call, and it says MTP "amortises over long generations".
# T2 is the binding constraint for the deciding artifact — measured at 1100-1188 ms
# against a 1200 ms budget with the cache off, i.e. a wall of 504s across 1000 items —
# while MTP only helps the sanctioned answer, which is streamed and not latency-gated.
# So: cache on, MTP off by default. Set AIRLOCK_SPEC_DECODE to restore it.
#
# VLLM_USE_FLASHINFER_MOE_FP4=0 (NFR-S5) trips a vLLM bug on this build: with it set,
# select_nvfp4_moe_backend() does list.remove() on a backend that is not in the candidate
# list and the engine dies with "ValueError: list.remove(x): x not in list". Left unset,
# vLLM auto-selects and logs "Using 'MARLIN' NvFp4 MoE backend" by itself — which is what
# NFR-S5 was asking for. Verified empirically: the model then generates coherent English,
# so the sm121 garbage-output failure the rule guards against is not occurring.
#
# --moe-backend is a GLOBAL flag, but this checkpoint is MIXED_PRECISION: some MoE
# layers are NVFP4 and some are left unquantized. vLLM picks MARLIN for the NVFP4 ones
# by itself ("Using 'MARLIN' NvFp4 MoE backend"), then map_unquantized_backend() rejects
# marlin for the unquantized ones and the engine dies. Leaving AIRLOCK_MOE_BACKEND unset
# lets vLLM choose per layer, which still satisfies NFR-S5's intent — marlin on the NVFP4
# MoE — without forcing it where it cannot apply. Set it to override.
ENTRY=(${AIRLOCK_VLLM_ENTRY:-})
EXTRA=(${AIRLOCK_VLLM_EXTRA:-})


bash "$(dirname "$0")/preflight.sh"

docker run -d --name airlock-text --gpus all \
  -p 127.0.0.1:8000:8000 \
  -v "${AIRLOCK_MODELS_DIR:-/mnt/data/models}:/models:ro" \
  -e VLLM_MARLIN_USE_ATOMIC_ADD=1 \
  ${AIRLOCK_FLASHINFER_MOE_FP4:+-e VLLM_USE_FLASHINFER_MOE_FP4=$AIRLOCK_FLASHINFER_MOE_FP4} \
  -e CUTE_DSL_ARCH=sm_121a \
  "$IMAGE" \
  "${ENTRY[@]}" \
  "${EXTRA[@]}" \
  --model "$MODEL" \
  --served-model-name airlock-text \
  --host 0.0.0.0 --port 8000 \
  --gpu-memory-utilization 0.40 \
  --max-model-len 32768 \
  --max-num-seqs 8 \
  ${AIRLOCK_MOE_BACKEND:+--moe-backend $AIRLOCK_MOE_BACKEND} \
  --kv-cache-dtype fp8 \
  --limit-mm-per-prompt '{"image":0,"video":0}' \
  --enable-prefix-caching \
  ${AIRLOCK_SPEC_DECODE:+--speculative-config "$AIRLOCK_SPEC_DECODE"}

echo "airlock-text launching. Whiteboard: +0.40. First compile 25-57 s — NOT a hang."
echo "Next: stack/warm.sh once /health returns 200."
