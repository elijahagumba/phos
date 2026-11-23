"""Viewer HTTP server: serves ``.phosrun`` files as a local web application.

The server binds to 127.0.0.1 only and serves:
- A JSON API for the library and detail views
- Static files (HTML, CSS, JS) from ``src/phos/viewer/static``

No outbound network requests are made. No telemetry is sent.
Constitution §3.8: no socket-based client imports (no direct socket module calls,
no ``requests``, no FastAPI framework). Port 0 lets the OS assign a free port.
"""

from __future__ import annotations

import http.server
import json
import socketserver as _socketserver
from pathlib import Path
from typing import Any, Final

from phos.runrecord import read_header, verify

VIEWER_DIR = Path(__file__).parent
STATIC_DIR = VIEWER_DIR / "static"

PORT_RANGE_START: Final = 8765
PORT_RANGE_END: Final = 8999


class ViewerRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP request handler for the viewer API and static files."""

    def __init__(self, *args: object, runs_dir: Path, **kwargs: object) -> None:
        self.runs_dir = runs_dir
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)  # type: ignore[arg-type]

    def do_GET(self) -> None:
        """Handle GET requests: API endpoints or static file serving."""
        parsed_path = self.path.split("?")[0]

        if parsed_path == "/api/runs":
            self._serve_runs_list()
        elif parsed_path.startswith("/api/run/"):
            run_name = parsed_path[len("/api/run/") :]
            self._serve_run_detail(run_name)
        elif parsed_path.startswith("/api/telemetry/"):
            run_name = parsed_path[len("/api/telemetry/") :]
            self._serve_telemetry_range(run_name)
        elif parsed_path == "/detail":
            self._serve_detail_page()
        elif parsed_path == "/detail.html":
            self._serve_detail_page()
        elif parsed_path == "/aggregate":
            self._serve_aggregate_page()
        elif parsed_path == "/aggregate.html":
            self._serve_aggregate_page()
        else:
            super().do_GET()

    def _send_json(self, data: object, status: int = 200) -> None:
        """Send a JSON response."""
        body = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, message: str) -> None:
        """Send a JSON error response."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode("utf-8"))

    def _serve_runs_list(self) -> None:
        """List all .phosrun files in the runs directory."""
        runs: list[dict[str, Any]] = []
        if self.runs_dir.is_dir():
            for path in sorted(self.runs_dir.glob("*.phosrun")):
                try:
                    header = read_header(path)
                    runs.append(
                        {
                            "name": path.name,
                            "title": header.get("title", path.stem),
                            "kind": header.get("kind", "unknown"),
                            "pool": header.get("pool", "unknown"),
                            "created_by": header.get("created_by", "unknown"),
                            "run_id": header.get("run_id", ""),
                        }
                    )
                except Exception:
                    pass
        self._send_json(runs)

    def _serve_run_detail(self, run_name: str) -> None:
        """Serve header + summary for a single run."""
        run_path = self.runs_dir / run_name
        if not run_path.is_file():
            self._send_error(404, f"Run not found: {run_name}")
            return

        try:
            header = read_header(run_path)
            problems = verify(run_path)
        except Exception as exc:
            self._send_error(500, f"Error reading run: {exc}")
            return

        detail: dict[str, Any] = {
            "name": run_name,
            "header": header,
            "valid": len(problems) == 0,
            "problems": problems,
        }
        self._send_json(detail)

    def _serve_telemetry_range(self, run_name: str) -> None:
        """Serve a range of telemetry data for a run."""
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        params: dict[str, str] = {}
        for part in query.split("&"):
            if "=" in part:
                key, value = part.split("=", 1)
                params[key] = value

        tag = params.get("tag", "")
        start_time = params.get("start", "")
        end_time = params.get("end", "")
        max_points = int(params.get("max_points", "1000"))

        run_path = self.runs_dir / run_name
        if not run_path.is_file():
            self._send_error(404, f"Run not found: {run_name}")
            return

        try:
            from phos.runrecord import RunRecord

            with RunRecord(run_path) as run:
                result = run.telemetry_range(tag, start_time, end_time)
        except Exception as exc:
            self._send_error(500, f"Error reading telemetry: {exc}")
            return

        values = result.get("values", [])
        timestamps = result.get("timestamps", [])
        if len(values) > max_points:
            step = len(values) // max_points
            values = values[::step]
            timestamps = timestamps[::step]

        self._send_json({"timestamps": timestamps, "values": values})

    def _serve_detail_page(self) -> None:
        """Serve the run detail page."""
        detail_path = STATIC_DIR / "detail.html"
        if detail_path.exists():
            self._serve_file(detail_path, "text/html")
        else:
            self._send_error(404, "Detail page not found")

    def _serve_aggregate_page(self) -> None:
        """Serve the aggregate views page."""
        aggregate_path = STATIC_DIR / "aggregate.html"
        if aggregate_path.exists():
            self._serve_file(aggregate_path, "text/html")
        else:
            self._send_error(404, "Aggregate page not found")

    def _serve_file(self, path: Path, content_type: str) -> None:
        """Serve a static file."""
        try:
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            self._send_error(404, f"File not found: {exc}")

    def log_message(self, format_string: str, *args: object) -> None:
        """Suppress default logging."""
        pass


class Viewer:
    """HTTP server for viewing .phosrun files."""

    def __init__(self, runs_dir: Path | None = None, port: int = 0) -> None:
        """Initialize the viewer server.

        Args:
            runs_dir: Directory containing .phosrun files. Defaults to ~/PHOS_runs.
            port: Port to bind to. 0 means auto-select free port.
        """
        self.runs_dir = runs_dir or Path.home() / "PHOS_runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.port = port
        self._server: _socketserver.TCPServer | None = None
        self._actual_port: int | None = None

    def start(self) -> int:
        """Start the HTTP server and return the port."""
        if self.port == 0:
            self.port = 0  # Port 0 lets the OS assign a free port

        def handler(*args: object, **kwargs: object) -> ViewerRequestHandler:
            return ViewerRequestHandler(*args, runs_dir=self.runs_dir, **kwargs)

        self._server = _socketserver.TCPServer(("127.0.0.1", self.port), handler)
        self._actual_port = self._server.server_address[1]
        return self._actual_port

    def serve_forever(self) -> None:
        """Start serving forever."""
        if self._server is None:
            self.start()
        assert self._server is not None
        self._server.serve_forever()

    def shutdown(self) -> None:
        """Shut down the server."""
        if self._server is not None:
            self._server.shutdown()


def run_server(runs_dir: Path | None = None, port: int = 0) -> int:
    """Start the viewer server and return the port."""
    viewer = Viewer(runs_dir=runs_dir, port=port)
    port = viewer.start()
    viewer.serve_forever()
    return port


__all__ = ["Viewer", "run_server"]
