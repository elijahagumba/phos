"""Pin that the research core stays offline (Constitution §3.8).

This is not a product security audit. It is a source-shape check: ``src/phos`` must not grow a
network client, a FastAPI app, or a UI tree. A green result is not live-site readiness.

``import socket`` is allowed. ``src/phos/atlas/packet/capture.py`` uses ``socket.inet_ntop`` and
``AF_INET`` to format packed addresses. ``socket.socket`` and ``socket.create_connection`` are not.
"""

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CORE = _REPO_ROOT / "src" / "phos"

# Substrings that mean a network client or a product HTTP surface, not address formatting.
_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "socket.socket",
    "socket.create_connection",
    ".connect(",
    "httpx",
    "fastapi",
    "uvicorn",
    "urllib.request",
)

_REQUESTS_IMPORT = re.compile(r"(?m)^\s*(?:import\s+requests\b|from\s+requests\b)")
_REQUESTS_ATTR = re.compile(r"\brequests\.")

_ABSENT_TREES: tuple[str, ...] = (
    "src/phos/api",
    "src/phos/intelligence",
    "ui",
)


def _core_python_files() -> list[Path]:
    """Return every ``.py`` file under ``src/phos``, in a stable order."""
    return sorted(path for path in _CORE.rglob("*.py") if path.is_file())


def _requests_as_network_client(source: str) -> bool:
    """Return True when ``requests`` is imported or used as an HTTP client."""
    return _REQUESTS_IMPORT.search(source) is not None or _REQUESTS_ATTR.search(source) is not None


def _forbidden_hits(source: str) -> list[str]:
    """Return the forbidden tokens present in ``source``."""
    hits = [token for token in _FORBIDDEN_SUBSTRINGS if token in source]
    if _requests_as_network_client(source):
        hits.append("requests.")
    return hits


def test_core_python_contains_no_network_clients() -> None:
    files = _core_python_files()
    assert files, "src/phos must contain Python files to scan"

    offenders: list[str] = []
    for path in files:
        hits = _forbidden_hits(path.read_text(encoding="utf-8"))
        if hits:
            relative = path.relative_to(_REPO_ROOT).as_posix()
            offenders.append(f"{relative}: {', '.join(hits)}")

    assert offenders == [], (
        "Constitution §3.8: the core is pure and offline; these files look like a network client: "
        + "; ".join(offenders)
    )


def test_import_socket_is_allowed_only_for_address_formatting() -> None:
    capture = _CORE / "atlas" / "packet" / "capture.py"
    text = capture.read_text(encoding="utf-8")
    assert "import socket" in text
    assert "socket.inet_ntop" in text
    assert "socket.AF_INET" in text
    assert "socket.socket" not in text
    assert "socket.create_connection" not in text


def test_product_surface_trees_are_absent() -> None:
    present = [relative for relative in _ABSENT_TREES if (_REPO_ROOT / relative).exists()]
    assert present == [], (
        "Constitution §3.8: api, intelligence, and ui must not exist as code trees; found "
        + ", ".join(present)
    )
