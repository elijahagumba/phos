"""PHOS viewer: local HTTP server for inspecting .phosrun files.

PART V3. The viewer is a thin, local-only web application that renders
``.phosrun`` files produced by ``phos-synth generate --write-phosrun`` or the
``phos.referee.record`` module.

Design constraints (V0):
- Binds to 127.0.0.1 only; no outbound network requests; no telemetry.
- All assets vendored in the repo with licences recorded; no CDN links.
- No JavaScript build toolchain; front end runs from plain files.
- Read-only with respect to run files; notes/stars live in a separate sidecar.
- Permissive licences only for any dependency; prefer stdlib + numpy.
- Never imports ``phos.atlas`` or anything under ``src/phos/atlas/``.
"""

from __future__ import annotations

from .server import Viewer, run_server

__all__ = ["Viewer", "run_server"]
