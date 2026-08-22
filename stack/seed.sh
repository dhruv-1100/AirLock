#!/usr/bin/env bash
# stack/seed.sh — owner C. Wrapper around stack/seed.js + bench/seed_corpus.py.
#
#   bash stack/seed.sh              # schema + indexes + corpus
#   bash stack/seed.sh --reseed     # drop `decisions` first (console sees an invalidate)
#   bash stack/seed.sh --schema     # schema and indexes only, no embeddings
#
# The seed BLOCKS on search-index readiness. That wait is deliberate: a $vectorSearch
# against a non-queryable index returns empty results rather than an error (R10), which
# looks exactly like a broken detector and sends the team debugging the wrong layer.
set -euo pipefail

URI="mongodb://localhost:27017/?directConnection=true"
NAME="airlock-mongo"
RESEED=0; SCHEMA_ONLY=0

for a in "$@"; do
  case "$a" in
    --reseed)  RESEED=1 ;;
    --schema)  SCHEMA_ONLY=1 ;;
    *) echo "unknown argument: $a" >&2; exit 1 ;;
  esac
done

say() { printf '\033[1;36m[seed]\033[0m %s\n' "$*"; }

# mongosh may not be on the host PATH; the container always has it.
run_js() {
  if command -v mongosh >/dev/null 2>&1; then
    mongosh "$URI" "$@"
  else
    say "using mongosh inside the container"
    docker exec -i "$NAME" mongosh "$URI" "$@"
  fi
}

if [ "$RESEED" = 1 ]; then
  say "re-seeding: dropping \`decisions\`"
  say "  the console will see an invalidate — stream.py flips resumeAfter -> startAfter"
  say "  and survives it. If the console dies here, that transition is the thing to check."
  run_js --eval 'DROP_DECISIONS=true' stack/seed.js < /dev/null
else
  if command -v mongosh >/dev/null 2>&1; then
    mongosh "$URI" stack/seed.js
  else
    docker exec -i "$NAME" mongosh "$URI" < stack/seed.js
  fi
fi

if [ "$SCHEMA_ONLY" = 1 ]; then
  say "schema only — skipping corpus embeddings"
  exit 0
fi

say "seeding policy_corpus (clauses + exemplars, CPU embeddings per NFR-S10)"
python3 bench/seed_corpus.py

printf '\n'
say "done. Verify retrieval is live before trusting a verdict's cited clause:"
say "  mongosh \"$URI\" --eval 'db.policy_corpus.aggregate([{\$listSearchIndexes:{}}])'"
