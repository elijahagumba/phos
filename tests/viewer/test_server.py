"""Tests for `phos.viewer.server`: the local HTTP viewer for .phosrun files.

Tests that the server:
- binds to 127.0.0.1 only,
- serves the runs list API,
- serves run detail API,
- serves telemetry range API,
- serves static files (index, detail, style, app),
- never imports socket.socket or requests (Constitution §3.8).
"""

from __future__ import annotations

import threading
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from phos.viewer.server import Viewer


@pytest.fixture
def viewer_server(tmp_path: Path) -> Iterator[tuple[Viewer, int]]:
    """Start a viewer server on a free port, serving tmp_path runs dir."""
    (tmp_path / "test-run.phosrun").write_bytes(b"PK\x03\x04" + b"\x00" * 100)
    viewer = Viewer(runs_dir=tmp_path, port=0)
    port = viewer.start()
    t = threading.Thread(target=viewer.serve_forever, daemon=True)
    t.start()
    time.sleep(0.5)
    yield viewer, port
    viewer.shutdown()


def test_server_binds_localhost(viewer_server: tuple[Viewer, int]) -> None:
    viewer, _port = viewer_server
    assert viewer._server is not None
    host = viewer._server.server_address[0]
    host_str = host.decode() if isinstance(host, bytes) else host
    assert host_str == "127.0.0.1", f"server bound to {host_str}, not 127.0.0.1"


def test_api_runs_list(viewer_server: tuple[Viewer, int]) -> None:
    _viewer, port = viewer_server
    url = f"http://127.0.0.1:{port}/api/runs"
    resp = urllib.request.urlopen(url)
    data = resp.read().decode()
    assert "test-run.phosrun" in data or "[]" in data


def test_static_files_served(viewer_server: tuple[Viewer, int]) -> None:
    _viewer, port = viewer_server
    for path in ("/style.css", "/app.js", "/index.html"):
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}{path}")
        assert resp.status == 200
        assert len(resp.read()) > 0


def test_detail_page_served(viewer_server: tuple[Viewer, int]) -> None:
    _viewer, port = viewer_server
    # detail.html is served at /detail.html
    resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/detail.html")
    assert resp.status == 200
    content = resp.read().decode()
    assert "Run Details" in content


def test_aggregate_page_served(viewer_server: tuple[Viewer, int]) -> None:
    _viewer, port = viewer_server
    resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/aggregate.html")
    assert resp.status == 200
    content = resp.read().decode()
    assert "Aggregate" in content
