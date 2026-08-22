#!/usr/bin/env bash
# NFR-S13 watchdog + the FREEZE protocol commands, one terminal, all day.
# If MemAvailable < 8 GB: stop airlock-vision IMMEDIATELY, drop caches,
# relaunch — not "wait and see". Second firing → consider headless (NFR-S14).
set -uo pipefail

THRESHOLD_GB="${1:-8}"

while true; do
  AVAIL_KB=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
  AVAIL_GB=$((AVAIL_KB / 1024 / 1024))
  SWAP_KB=$(grep SwapFree /proc/meminfo | awk '{print $2}')
  APPS=$(nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory \
         --format=csv,noheader 2>/dev/null | tr '\n' ' | ')
  printf '%s  avail %2d GB  swapfree %d KB  gpu: %s\n' \
         "$(date +%H:%M:%S)" "$AVAIL_GB" "$SWAP_KB" "${APPS:-none}"
  if [ "$AVAIL_GB" -lt "$THRESHOLD_GB" ]; then
    echo
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "!!! MemAvailable ${AVAIL_GB} GB < ${THRESHOLD_GB} GB — NFR-S13 FIRED"
    echo "!!! Say FREEZE out loud. Then, immediately:"
    echo "!!!   docker stop airlock-vision"
    echo "!!!   sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'"
    echo "!!!   bash stack/launch_vision.sh   # when stable"
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
  fi
  sleep 5
done
