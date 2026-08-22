#!/usr/bin/env bash
# Serves the standalone projector console on http://localhost:5174.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -m http.server 5174 --bind 127.0.0.1
