#!/usr/bin/env bash
# Gate G0 + NFR-S2 — run BEFORE EVERY vLLM launch, in this order. Owner: A.
#
# On this box OOM is not an exception: unbounded allocation hangs the whole
# host — no SSH, no ping (pytorch/pytorch#174358). This script is the ritual
# that prevents that. Exit 0 = clear to launch; exit 1 = HARD STOP.
set -uo pipefail

echo "=== AIRLOCK preflight $(date +%H:%M:%S) ==="

# 1. Swap off — OS page cache competes with CUDA for the same 128 GB pool.
sudo swapoff -a && echo "[ok] swap off"

# 2. Drop caches.
sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches' && echo "[ok] caches dropped"

# 3. Driver gate (G0): must be 580.x. 590.x deadlocks CUDAGraph — HARD STOP,
#    not a warning. Fallback per SRS §11 G0: driver rollback owned by A,
#    15-minute budget, else demo on --enforce-eager and say so.
DRIVER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null)
echo "driver: ${DRIVER:-UNREADABLE}"
case "$DRIVER" in
  580.*) echo "[ok] driver 580.x" ;;
  590.*) echo "[G0 FAIL] driver 590.x — CUDAGraph deadlock. STOP. SHOUT. Do not launch."; exit 1 ;;
  *)     echo "[G0 WARN] unexpected driver '$DRIVER' — treat as inconclusive, escalate"; exit 1 ;;
esac

# 4. Baseline memory, recorded.
free -h | tee /tmp/baseline_free.txt
AVAIL_KB=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
echo "MemAvailable: $((AVAIL_KB / 1024 / 1024)) GB"
if [ "$AVAIL_KB" -lt $((8 * 1024 * 1024)) ]; then
  echo "[FAIL] under 8 GB available BEFORE launch (NFR-S13 territory). Investigate first."
  exit 1
fi

# 5. Container images present (pre-staged — do NOT pull now).
docker images | grep -E 'vllm|hellohal' || {
  echo "[FAIL] vLLM images missing — they were pre-staged on the USB"; exit 1; }

# 6. Mongo before models (NFR-S6): C's container must be up with heap verified.
if [ "$(docker inspect -f '{{.State.Health.Status}}' airlock-mongo 2>/dev/null)" = "healthy" ]; then
  echo "[ok] airlock-mongo healthy — confirm C has CALLED 'mongo heap verified' out loud"
else
  echo "[WAIT] airlock-mongo not healthy. NFR-S6: mongo starts BEFORE any model."
  echo "       Do not launch until C's heap check passes (<=10:08)."
  exit 1
fi

echo
echo "=== CLEAR TO LAUNCH. Whiteboard rules (NFR-S1/S3): ==="
echo "  - write the new summed --gpu-memory-utilization BEFORE launching"
echo "  - committed demo total 0.68 | hard ceiling 0.85 | text .40 vision .28"
echo "  - two-server config: T2 classification runs ON :8000 (see stack/models.env)"
