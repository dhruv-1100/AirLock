#!/usr/bin/env bash
# Text throughput sweep (SRS Phase 3 item 8, NFR-T1): c ∈ {1, 8, 64, 256},
# input 512 / output 256, --num-prompts max(32, c×4). Expect strong scaling
# (published GB10 precedent: 5.79 → 695 tok/s at c=256).
set -euo pipefail

TEXT_URL="${AIRLOCK_TEXT_URL:-http://127.0.0.1:8000}"
MODEL="${AIRLOCK_TEXT_MODEL:-Qwen/Qwen3.6-35B-A3B}"
OUT="results/text_sweep_$(date +%s)"
mkdir -p results

for c in 1 8 64 256; do
  n=$(( c * 4 > 32 ? c * 4 : 32 ))
  echo "=== concurrency $c, num_prompts $n ==="
  vllm bench serve \
    --base-url "$TEXT_URL" \
    --model "$MODEL" \
    --dataset-name random \
    --random-input-len 512 \
    --random-output-len 256 \
    --max-concurrency "$c" \
    --num-prompts "$n" \
    --ignore-eos \
    --save-result --result-filename "${OUT}_c${c}.json" \
    2>&1 | tee "${OUT}_c${c}.log"
done

echo "results in ${OUT}_c*.json"
