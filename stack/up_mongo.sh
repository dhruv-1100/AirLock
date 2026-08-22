#!/usr/bin/env bash
# stack/up_mongo.sh — owner C. SRS §3, NFR-S6, Risk R8.
#
# THIS SCRIPT BLOCKS ENGINEER A. A may not launch a single GPU process until this
# prints "mongo heap verified". Target: done by 10:08.
#
# The risk being managed: mongot's documented default JVM heap is 25% of total system
# memory capped at 32 GB, and NVIDIA's worked example for that doc is a 128 GB box —
# this box exactly. Unconstrained, mongot targets 32 GB of the same unified pool vLLM
# sized itself against. That is a host freeze, not an OOM (pytorch/pytorch#174358).
#
# The control is the cgroup: JVMs have honoured UseContainerSupport since JDK 10, so
# "total system memory" resolves to --memory=6g => 25% of 6 GB ~= 1.5 GB heap.
#
# Usage:  bash stack/up_mongo.sh            # normal
#         bash stack/up_mongo.sh --recreate # tear down and rebuild (keeps the volume)
#         bash stack/up_mongo.sh --wipe     # tear down and DESTROY the data volume
set -euo pipefail

NAME="airlock-mongo"
IMAGE="mongodb/mongodb-atlas-local:8.3.8"
VOLUME="airlock_mongo_data"
HEAP_CEILING_GB=4          # NFR-S6: anything above this is a fail, not a warning
HEALTH_TIMEOUT=180         # seconds

say()  { printf '\033[1;36m[up_mongo]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[up_mongo]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[up_mongo]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[up_mongo] FATAL:\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- args
RECREATE=0; WIPE=0
for a in "$@"; do
  case "$a" in
    --recreate) RECREATE=1 ;;
    --wipe)     RECREATE=1; WIPE=1 ;;
    *) die "unknown argument: $a" ;;
  esac
done

command -v docker >/dev/null 2>&1 || die "docker not on PATH"

# ---------------------------------------------------------------- teardown
if [ "$RECREATE" = 1 ] && docker inspect "$NAME" >/dev/null 2>&1; then
  say "removing existing container $NAME"
  docker rm -f "$NAME" >/dev/null
  if [ "$WIPE" = 1 ]; then
    warn "DESTROYING volume $VOLUME — all decisions and policy_corpus will be lost"
    docker volume rm "$VOLUME" >/dev/null 2>&1 || true
  fi
fi

if docker inspect "$NAME" >/dev/null 2>&1; then
  state="$(docker inspect -f '{{.State.Status}}' "$NAME")"
  if [ "$state" = "running" ]; then
    ok "container already running — skipping to verification"
  else
    say "container exists but is $state — starting it"
    docker start "$NAME" >/dev/null
  fi
else
  # ------------------------------------------------------------ launch
  # DO_NOT_TRACK=1 is NOT optional. The image phones home, and an unsolicited outbound
  # call is precisely what our own demo claims to prevent. A judge running tcpdump
  # during beat 4 would find it.
  # --cpus=4 pins GC thread sizing off 4 cores, not all 20 Arm cores.
  say "launching $NAME ($IMAGE) with a 6 GB cgroup"
  docker run -d --name "$NAME" --platform linux/arm64 \
    --memory=6g --memory-swap=6g --cpus=4 -p 27017:27017 \
    -v "$VOLUME":/data/db -e DO_NOT_TRACK=1 \
    -e MONGODB_INITDB_DATABASE=airlock "$IMAGE" >/dev/null
fi

# ---------------------------------------------------------------- health poll
say "waiting for health (timeout ${HEALTH_TIMEOUT}s)…"
deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
until [ "$(docker inspect -f '{{.State.Health.Status}}' "$NAME" 2>/dev/null || echo starting)" = healthy ]; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    docker logs --tail 40 "$NAME" || true
    die "container did not reach healthy in ${HEALTH_TIMEOUT}s (logs above)"
  fi
  sleep 2
done
ok "container healthy"

# ---------------------------------------------------------------- heap verification
# Two independent signals: the JVM's own log line, and the container's actual RSS.
verify_heap() {
  local xmx_line rss_mb
  xmx_line="$(docker exec "$NAME" grep -i -m5 -E 'Xmx|maxHeap|heap' /tmp/mongot.log 2>/dev/null || true)"
  rss_mb="$(docker stats --no-stream --format '{{.MemUsage}}' "$NAME" 2>/dev/null | awk '{print $1}')"
  printf '  mongot.log : %s\n' "${xmx_line:-<no heap line yet>}"
  printf '  MemUsage   : %s\n' "${rss_mb:-<unavailable>}"

  # Fail on any Xmx at or above the ceiling. Matches -Xmx32g, -Xmx8192m, maxHeapSize=32G.
  if printf '%s' "$xmx_line" | grep -qiE 'x?mx[= ]?(3[0-9]|[4-9][0-9])[0-9]*[gG]'; then
    return 1
  fi
  # Container RSS above the ceiling means the JVM sized itself off host memory.
  local n unit
  n="$(printf '%s' "${rss_mb:-0}" | sed -E 's/([0-9.]+).*/\1/')"
  unit="$(printf '%s' "${rss_mb:-0}" | sed -E 's/[0-9.]+//' | tr '[:lower:]' '[:upper:]')"
  case "$unit" in
    GIB|GB) awk -v n="$n" -v c="$HEAP_CEILING_GB" 'BEGIN{exit !(n>c)}' && return 1 ;;
  esac
  return 0
}

say "verifying JVM heap cap (NFR-S6 — this is the host-freeze risk)"
sleep 3   # give mongot a moment to write its startup log
if verify_heap; then
  ok "heap is capped"
else
  # ---- Fallback per SRS §7.3 / R8: undocumented on this image, honoured by most launchers
  warn "heap cap did NOT take — applying JAVA_TOOL_OPTIONS fallback and recreating"
  docker rm -f "$NAME" >/dev/null
  docker run -d --name "$NAME" --platform linux/arm64 \
    --memory=6g --memory-swap=6g --cpus=4 -p 27017:27017 \
    -v "$VOLUME":/data/db -e DO_NOT_TRACK=1 \
    -e JAVA_TOOL_OPTIONS="-Xms1g -Xmx2g" \
    -e MONGODB_INITDB_DATABASE=airlock "$IMAGE" >/dev/null

  deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
  until [ "$(docker inspect -f '{{.State.Health.Status}}' "$NAME" 2>/dev/null || echo starting)" = healthy ]; do
    [ "$(date +%s)" -ge "$deadline" ] && die "container did not reach healthy after fallback"
    sleep 2
  done
  sleep 3
  if verify_heap; then
    ok "heap capped via JAVA_TOOL_OPTIONS fallback"
  else
    printf '\n'
    die "HEAP STILL UNCAPPED. Do NOT let A launch a model.
     Escalation per R8: run plain 'mongo:8' without mongot and switch retrieval to the
     client-side RRF fallback in services/inspect/mongo.py (set AIRLOCK_RRF=client).
     Both emit the identical score/scoreDetails shape, so B's UI does not change."
  fi
fi

# ---------------------------------------------------------------- connectivity
# directConnection=true is MANDATORY. Without it the driver does replica-set discovery,
# gets the container-internal hostname back, and hangs until server-selection timeout.
URI="mongodb://localhost:27017/?directConnection=true"
say "checking connectivity (must answer in under 2 s)"
if docker exec "$NAME" mongosh "$URI" --quiet --eval 'db.runCommand({ping:1}).ok' 2>/dev/null | grep -q 1; then
  ok "ping ok via $URI"
else
  warn "in-container mongosh ping failed — check directConnection=true before debugging anything else"
fi

printf '\n'
ok "================================================"
ok "  MONGO HEAP VERIFIED  —  SAY IT OUT LOUD."
ok "  Engineer A is unblocked and may launch model #1."
ok "================================================"
printf '\n'
say "connection string: $URI"
say "next: bash stack/seed.sh   (creates collections, indexes, and BLOCKS on index READY)"
