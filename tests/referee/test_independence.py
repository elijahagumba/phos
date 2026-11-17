"""Nothing the referee calls is allowed to call the referee back.

PART S6. The referee may import `phos.synth` and `phos.atlas`'s public surfaces; the reverse must
never be true, or a generator or an engine could end up depending on how it is being examined.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

BANNED_PACKAGES = ("phos.synth", "phos.eval", "phos.models", "phos.atlas")


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


def _reaches_referee(names: set[str]) -> list[str]:
    return sorted(
        name for name in names if name == "phos.referee" or name.startswith("phos.referee.")
    )


def test_the_scan_finds_enough_modules_to_mean_something() -> None:
    assert len(_modules("phos.synth")) >= 2
    assert len(_modules("phos.atlas")) >= 2


@pytest.mark.parametrize("package", BANNED_PACKAGES)
def test_no_module_imports_the_referee(package: str) -> None:
    for path in _modules(package):
        offending = _reaches_referee(_imported(path))
        assert not offending, f"{package}/{path.name} imports {offending}"
