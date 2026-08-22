#!/usr/bin/env bash
# Serves the replica composer on http://localhost:5173.
# Loopback -> loopback: Local Network Access is not involved on this surface at all.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -m http.server 5173 --bind 127.0.0.1
