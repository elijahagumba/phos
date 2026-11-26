"""The two refused lane-E modules stay on disk and stay off the law page (ADR 0400).

`drift_consistency` (lane 3, refused by ADR 0286 on delay) and `placement_consistency` (the
first-crossing rule, refused by ADR 0399 on three of four bars) are kept so those records stay
reproducible. Neither is declared, and nothing on the law page may import either.

The tests are static: they read source text and parse it, so they hold whether or not the modules
are importable, and they fail if a future session wires one of them into the law page by any of the
routes that would matter — a direct import, an import of its script, or a call reached through a
third module.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from phos.atlas.declared_law import LAWS, OPERATOR_PAGE_CEILING

_SRC = Path(__file__).resolve().parents[2] / "src" / "phos" / "atlas"
_LAW_PAGE = _SRC / "declared_law.py"
_LAW_INLET = _SRC / "law_inlet.py"
_REFUSED = ("drift_consistency", "placement_consistency")


def _imported_modules(path: Path) -> set[str]:
    """Every module named by an `import` or `from ... import` in `path`.

    Returns the trailing dotted component for each, so `phos.atlas.drift_consistency` and
    `from phos.atlas import drift_consistency` both yield `drift_consistency`.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[-1] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                found.add(node.module.split(".")[-1])
            found.update(alias.name for alias in node.names)
    return found


@pytest.mark.parametrize("module", _REFUSED)
def test_the_refused_module_is_still_on_disk(module: str) -> None:
    """It stays so ADR 0286's and ADR 0399's numbers can be regenerated under their own names."""
    assert (_SRC / f"{module}.py").is_file(), f"{module}.py was deleted; its record loses its code"


@pytest.mark.parametrize("module", _REFUSED)
def test_the_law_page_does_not_import_it(module: str) -> None:
    assert module not in _imported_modules(_LAW_PAGE)


@pytest.mark.parametrize("module", _REFUSED)
def test_the_law_inlet_does_not_import_it(module: str) -> None:
    assert module not in _imported_modules(_LAW_INLET)


def test_the_refused_modules_are_not_among_the_six_laws() -> None:
    """A placement rule is not a law, and adding one would change the page's contract."""
    names = {law.name for law in LAWS}
    assert len(names) == 6
    assert names == {
        "joint_move",
        "subfloor_walk",
        "band_handoff",
        "program_transfer",
        "allowed_writer",
        "controller_valve",
    }
    assert OPERATOR_PAGE_CEILING == 8


def test_no_atlas_module_imports_a_refused_module_except_its_own_script() -> None:
    """The pair may be reached from their lane scripts and their tests, and from nowhere else.

    A residual detector that quietly became an import of the live engine would be undeclared
    promotion by the back door. `scripts/` is not scanned: those files exist to run exactly these
    modules, under their own refused result names.
    """
    offenders: list[str] = []
    for path in sorted(_SRC.glob("*.py")):
        if path.stem in _REFUSED:
            continue
        imported = _imported_modules(path)
        for module in _REFUSED:
            if module in imported:
                offenders.append(f"{path.name} imports {module}")
    assert offenders == []
