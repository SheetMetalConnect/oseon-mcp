#!/usr/bin/env bash
# Foreground stdio launcher; the MCP host owns process lifetime.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
exec uv run --locked python -m trumpf_oseon_mcp
