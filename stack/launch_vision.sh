#!/usr/bin/env bash
# airlock-vision :8001 — --gpu-memory-utilization 0.28.
# Owner: A. ONLY A runs this (NFR-S1). Run stack/preflight.sh FIRST.
#
# RE-CUT for the pre-staged weights (stack/models.env): Nemotron-3-Nano-Omni
# 30B A3B is 21 GB of BF16 weights on disk — before KV, MM caches and graphs.
# SRS 0.24 (~31 GB) was sized for a 7B; 0.28 ≈ 36.1 GB fits
# 21w + ~8 KV (max-num-seqs 4) + ~3 MM caches + ~3 graphs with margin.
# Two-server demo total: text 0.40 + vision 0.28 = 0.68 (ceiling 0.85).
#
# SM121-patched image is MANDATORY — stock vLLM images fail "SM121 not
# supported" for VLMs. FlashInfer lacks SM121 → --attention-backend TRITON_ATTN.
# The two MM cache caps are load-bearing: defaults are 8 GiB + 4 GiB PER
# PROCESS of "CPU RAM" which on GB10 is the same 128 GB pool — 15-20 GB of
# invisible consumption without them.
#
# Weights fallback ladder (SRS §3): Holo1.5-7B
#   → nvidia/Qwen2.5-VL-7B-Instruct-NVFP4 (NVIDIA-validated on Spark)
#   → Qwen/Qwen3-VL-8B-Instruct
set -euo pipefail

# stack/models.env maps the pre-staged weights onto the model roles —
# source it so the PATH (launch) / NAME (request) split cannot be mixed up.
if [ -f "$(dirname "$0")/models.env" ]; then
  set -a; . "$(dirname "$0")/models.env"; set +a
fi

MODEL="${AIRLOCK_VLM_MODEL_PATH:?set AIRLOCK_VLM_MODEL_PATH (weights path, e.g. /models/omni) — NOT AIRLOCK_VLM_MODEL, which is the request name}"
IMAGE="${AIRLOCK_VLM_IMAGE:-hellohal2064/vllm-dgx-spark-gb10}"

# Entrypoint shim. vllm/vllm-openai has ENTRYPOINT ["vllm","serve"], so bare flags work.
# nvcr.io/nvidia/vllm runs nvidia_entrypoint.sh, which execs its Cmd verbatim — bare
# flags give `exec: --: invalid option` and the container exits(2) in under a second.
# Empty default preserves the original behaviour exactly; models.env sets it when the
# NVIDIA image is in use. Also carries --trust-remote-code, which the Nemotron custom
# architectures require (the working af-vllm container passed it).
# min_pixels/max_pixels are Qwen2_5_VL processor arguments. The omni weights use
# NanoNemotronVLProcessor, which rejects them outright:
#   TypeError: NanoNemotronVLProcessor.__init__() got an unexpected keyword argument 'min_pixels'
# Left unset, the processor uses its own defaults. The pixel cap the SRS wanted is still
# enforced, just client-side: B's shrinkToB64() downscales to a 1024 px long edge before
# the payload ever leaves the tab, so the server never sees a full-resolution image.
# The OpenShell gateway's Privacy Router runs in a container and resolves the host as
# host.openshell.internal -> the docker bridge. A loopback-only publish is unreachable
# from there, so `openshell inference set` fails verification and the sandbox has no
# local model to route to. Publishing on the bridge as well keeps the listener off the
# LAN — it is reachable only from containers on this box — while making the local-first
# inference path actually work. Unset AIRLOCK_BRIDGE_IP to go back to loopback only.
ENTRY=(${AIRLOCK_VLLM_ENTRY:-})
EXTRA=(${AIRLOCK_VLLM_EXTRA:-})


bash "$(dirname "$0")/preflight.sh"

docker run -d --name airlock-vision --gpus all \
  -p 127.0.0.1:8001:8001 \
  ${AIRLOCK_BRIDGE_IP:+-p $AIRLOCK_BRIDGE_IP:8001:8001} \
  -v "${AIRLOCK_MODELS_DIR:-/mnt/data/models}:/models:ro" \
  -e VLLM_MARLIN_USE_ATOMIC_ADD=1 \
  ${AIRLOCK_FLASHINFER_MOE_FP4:+-e VLLM_USE_FLASHINFER_MOE_FP4=$AIRLOCK_FLASHINFER_MOE_FP4} \
  -e CUTE_DSL_ARCH=sm_121a \
  -e VLLM_MM_INPUT_CACHE_GIB=2 \
  "$IMAGE" \
  "${ENTRY[@]}" \
  "${EXTRA[@]}" \
  --model "$MODEL" \
  --served-model-name airlock-vision \
  --host 0.0.0.0 --port 8001 \
  --gpu-memory-utilization 0.28 \
  --max-num-seqs 4 \
  --attention-backend TRITON_ATTN \
  ${AIRLOCK_MM_PROCESSOR_KWARGS:+--mm-processor-kwargs "$AIRLOCK_MM_PROCESSOR_KWARGS"} \
  --mm-processor-cache-gb 1 \
  --limit-mm-per-prompt '{"image":1,"video":0}'

echo "airlock-vision launching. Whiteboard: +0.28 (two-server running total should read 0.68 with text)."
echo "NO speculative decoding here — we emit ≤8 tokens (NFR-S8 companion rule)."
echo "Next: stack/warm.sh, then bench/vision_gate.py — that is Gate G1 at 10:45."
