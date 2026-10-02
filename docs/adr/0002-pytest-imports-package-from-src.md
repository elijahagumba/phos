# ADR 0002 — pytest imports `phos` from `src/`, not from the editable install

- **Status:** Accepted
- **Date:** 2026-07-28
- **PART:** 1 — Core Ontology & Evidence Store

## Context

The repo uses a src layout and `uv sync` installs `phos` into `.venv` in editable mode via a
`.pth` file. On this macOS development machine every `.pth` file uv writes into the venv ends up
carrying the `UF_HIDDEN` file flag. CPython 3.11+ deliberately **skips hidden `.pth` files**
(`site.addpackage` checks `st_flags & UF_HIDDEN`), so `src/` never reaches `sys.path` and
`import phos` fails.

The failure is intermittent and misleading: the suite passes immediately after an explicit
`uv sync --reinstall-package phos`, then breaks again the next time uv rebuilds the project —
which it does whenever a source file changes. `mypy` and `ruff` are unaffected because they are
configured with their own source roots.

## Decision

Set `pythonpath = ["src"]` in `[tool.pytest.ini_options]` so pytest puts the source tree on
`sys.path` itself. The test suite no longer depends on the state of the editable install.

## Consequences

- `uv run pytest` works deterministically regardless of venv or platform quirks — which is what
  Constitution §3.7 asks for.
- Tests exercise the source tree directly, so a packaging mistake (a module missing from the
  built wheel) would not be caught by the test suite. That risk is accepted for now; the API PART
  will exercise an installed package and would surface it.
- `chflags nohidden .venv/lib/python3.12/site-packages/*.pth` repairs an already-broken venv if
  anything else in the toolchain needs the editable install.
