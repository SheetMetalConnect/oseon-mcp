#!/usr/bin/env bash
# @raycast.schemaVersion 1
# @raycast.title Oseon MCP offline tests
# @raycast.mode fullOutput
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
exec uv run --locked pytest -q
