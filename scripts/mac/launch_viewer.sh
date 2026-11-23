#!/bin/bash
# PHOS Viewer — Mac launcher
#
# Launches the PHOS viewer server on 127.0.0.1 and opens the default browser.
# No outbound network requests; all assets vendored locally.
#
# Usage:
#   ./scripts/mac/launch_viewer.sh              # Serve ~/PHOS_runs
#   ./scripts/mac/launch_viewer.sh /path/to/runs # Serve a specific directory

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.. && pwd)"
RUNS_DIR="${1:-$HOME/PHOS_runs}"

cd "$REPO_DIR"

if [ ! -d ".venv" ]; then
    echo "Error: .venv not found. Run 'uv sync' first." >&2
    exit 1
fi

echo "PHOS Viewer — launching on 127.0.0.1"
echo "Serving runs from: $RUNS_DIR"
echo ""

source .venv/bin/activate
exec python -m phos.viewer.cli --runs-dir "$RUNS_DIR" --no-browser
