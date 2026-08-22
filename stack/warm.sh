#!/usr/bin/env bash
# Warm-up loop — SRS §7.1 "Warm-up is not optional": the first request triggers
# torch.compile/inductor, 25-57 s. A cold first paste on stage is a lost demo.
# Run the moment /health returns 200, and AGAIN at 16:30 demo freeze.
set -uo pipefail

TEXT="${AIRLOCK_TEXT_URL:-http://127.0.0.1:8000}"
VLM="${AIRLOCK_VLM_URL:-http://127.0.0.1:8001}"
CLF="${AIRLOCK_CLF_URL_BASE:-http://127.0.0.1:8002}"

# 1x1 px PNG, base64 — the smallest possible compile trigger for the VLM.
PX="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

wait_health() { # url name
  echo -n "waiting for $2 /health "
  for _ in $(seq 1 300); do
    if curl -sf -o /dev/null "$1/health"; then echo "— up"; return 0; fi
    echo -n "."; sleep 2
  done
  echo "— TIMED OUT (10 min)"; return 1
}

warm_chat() { # url model body-extra name
  echo "warming $4 (first call may take 25-57 s of torch.compile — NOT a hang)"
  T0=$(date +%s)
  curl -sf -m 120 "$1/v1/chat/completions" -H 'Content-Type: application/json' \
    -d "$2" -o /dev/null \
    && echo "  $4 warm in $(( $(date +%s) - T0 )) s" \
    || echo "  [WARN] $4 warm-up call failed"
}

if wait_health "$TEXT" airlock-text; then
  warm_chat "$TEXT" '{"model":"airlock-text","max_tokens":4,"messages":[{"role":"user","content":"warm up"}]}' "" airlock-text
fi

if wait_health "$VLM" airlock-vision; then
  warm_chat "$VLM" '{"model":"airlock-vision","max_tokens":3,"messages":[{"role":"user","content":[{"type":"text","text":"describe"},{"type":"image_url","image_url":{"url":"data:image/png;base64,'"$PX"'"}}]}]}' "" airlock-vision
fi

if curl -sf -o /dev/null -m 2 "$CLF/health"; then
  warm_chat "$CLF" '{"model":"airlock-clf","max_tokens":4,"messages":[{"role":"user","content":"warm up"}]}' "" airlock-clf
else
  echo "airlock-clf not up — skipping (T2 may be routed to :8000)"
fi

echo "warm.sh done. Re-run this at 16:30 demo freeze."
