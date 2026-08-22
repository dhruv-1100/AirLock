#!/usr/bin/env bash
# Vision throughput sweep (SRS Phase 2 item 8, NFR-T2/T3/T4).
# Vision is prefill-bound: expect 1.5-2.5x from c=1 to c=8, then flat.
# Run TWICE per NFR-T4: once idle, once with the 35B under c=8 load —
# publish both columns.
set -euo pipefail

VLM_URL="${AIRLOCK_VLM_URL:-http://127.0.0.1:8001}"
MODEL="${AIRLOCK_VLM_MODEL:-Hcompany/Holo1.5-7B}"
TAG="${1:-idle}"   # "idle" or "loaded"
OUT="results/vision_sweep_${TAG}_$(date +%s)"
mkdir -p results

for c in 1 2 4 8 16; do
  echo "=== concurrency $c ($TAG) ==="
  vllm bench serve \
    --base-url "$VLM_URL" \
    --model "$MODEL" \
    --dataset-name random-mm \
    --random-mm-bucket-config '{(720, 1280, 1): 1.0}' \
    --random-output-len 8 \
    --max-concurrency "$c" \
    --num-prompts $((c * 4 > 32 ? c * 4 : 32)) \
    --ignore-eos \
    --save-result --result-filename "${OUT}_c${c}.json" \
    2>&1 | tee "${OUT}_c${c}.log"
done

echo "results in ${OUT}_c*.json — images/sec = num_prompts / wall-clock at the"
echo "largest c where E2E p95 <= 2.5 s (NFR-T3)"
