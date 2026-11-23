"""Independence: the breaker imports no Atlas or rule-exposing referee internals (PART S7).

The breaker may import ``phos.referee.seeds`` (seed pool management, no Atlas rules) but must never
import ``phos.atlas`` or any referee module that touches Atlas's rules, thresholds, models or
detection internals.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

# ``phos.atlas`` is entirely banned; within ``phos.referee`` only the seed-pool module is allowed.
BANNED_MODULES = (
    "phos.atlas",
    "phos.atlas.",
    "phos.referee.detectors",
    "phos.referee.detectors.",
    "phos.referee.scoring",
    "phos.referee.scoring.",
    "phos.referee.runner",
    "phos.referee.runner.",
    "phos.referee.corpus",
    "phos.referee.corpus.",
    "phos.referee.integrity",
    "phos.referee.integrity.",
)


def _modules(package: str) -> tuple[Path, ...]:
    module = importlib.import_module(package)
    location = module.__file__
    assert location is not None, f"{package} has no __file__"
    root = Path(location).parent
    return tuple(sorted(root.rglob("*.py")))


def _imported(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    reached: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            reached.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            reached.add(node.module)
    return reached


def _reaches_banned(names: set[str]) -> list[str]:
    return sorted(
        name for name in names if any(name == b or name.startswith(b) for b in BANNED_MODULES)
    )


def test_the_scan_finds_enough_modules_to_mean_something() -> None:
    assert len(_modules("phos.breaker")) >= 2


def test_no_module_imports_atlas_or_referee_internals() -> None:
    for path in _modules("phos.breaker"):
        offending = _reaches_banned(_imported(path))
        assert not offending, f"phos.breaker/{path.name} imports {offending}"


__all__ = []
