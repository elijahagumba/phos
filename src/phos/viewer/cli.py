"""The ``phos-view`` command: launch the viewer server and open a browser.

Usage::

    phos-view                    # Serve ~/PHOS_runs on a free port
    phos-view --runs-dir /path   # Serve a specific directory
    phos-view --port 8080        # Serve on a specific port
"""

from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

from phos.viewer.server import Viewer


def main(argv: list[str] | None = None) -> int:
    """Entry point for the phos-view CLI."""
    parser = argparse.ArgumentParser(
        prog="phos-view",
        description="Serve .phosrun files as a local web application.",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=None,
        help="Directory containing .phosrun files (default: ~/PHOS_runs)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Port to serve on (0 = auto-select free port)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start the server without opening a browser",
    )
    args = parser.parse_args(argv)

    viewer = Viewer(runs_dir=args.runs_dir, port=args.port)
    port = viewer.start()

    url = f"http://127.0.0.1:{port}"
    print(f"PHOS viewer running at {url}")
    print(f"Serving runs from: {viewer.runs_dir}")

    if not args.no_browser:
        webbrowser.open(url)

    try:
        viewer.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down viewer...")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
