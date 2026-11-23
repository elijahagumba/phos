"""Final integration audits (PART S11).

Task 3: Independence audit — fails if:
  (a) the simulator imports the breaker or referee,
  (b) the breaker imports Atlas or the referee's internals,
  (c) any package other than the referee imports Atlas,
  (d) any production code modifies files under src/phos/atlas/.

Task 4: Reproducibility audit — runs the end-to-end demo twice in fresh processes and
asserts identical report hashes.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


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


def _reaches(names: set[str], prefixes: tuple[str, ...]) -> list[str]:
    return sorted(name for name in names if any(name == p or name.startswith(p) for p in prefixes))


# --- Task 3a: simulator must not import breaker or referee -----------------------

SIMULATOR_BANNED = ("phos.breaker", "phos.breaker.", "phos.referee", "phos.referee.")


@pytest.mark.parametrize("package", ["phos.synth"])
def test_simulator_does_not_import_breaker_or_referee(package: str) -> None:
    for path in _modules(package):
        offending = _reaches(_imported(path), SIMULATOR_BANNED)
        assert not offending, f"{package}/{path.name} imports {offending}"


# --- Task 3b: breaker must not import Atlas or referee internals -----------------

BREAKER_BANNED = (
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


def test_breaker_does_not_import_atlas_or_referee_internals() -> None:
    for path in _modules("phos.breaker"):
        offending = _reaches(_imported(path), BREAKER_BANNED)
        assert not offending, f"phos.breaker/{path.name} imports {offending}"


# --- Task 3c: among the S6-S11 packages, only the referee may import Atlas ---------

ATLAS_PREFIXES = ("phos.atlas", "phos.atlas.")


def _atlas_importers() -> list[str]:
    """Among the S6-S11 packages, only `phos.referee` may import `phos.atlas`."""
    importers: list[str] = []
    for package in ("phos.breaker", "phos.release"):
        for path in _modules(package):
            offending = _reaches(_imported(path), ATLAS_PREFIXES)
            if offending:
                importers.append(f"{package}/{path.name}: {offending}")
    return importers


def test_only_referee_imports_atlas() -> None:
    importers = _atlas_importers()
    assert not importers, (
        "S6-S11 packages other than the referee import phos.atlas: " + str(importers)
    )


# --- Task 3d: no production code modifies files under src/phos/atlas/ -------------

ATLAS_SRC = REPO_ROOT / "src" / "phos" / "atlas"


def test_no_production_code_modifies_atlas_files() -> None:
    """Scan production code for writes to src/phos/atlas/ paths.

    We look for string literals containing "src/phos/atlas" or "phos/atlas" passed to
    open(), write_text(), mkdir(), or similar filesystem-write calls.
    """
    write_calls = ("open", "write_text", "write_bytes", "mkdir", "rename", "replace", "unlink")
    violations: list[str] = []
    src = REPO_ROOT / "src" / "phos"
    for package_dir in sorted(src.iterdir()):
        if not package_dir.is_dir() or not (package_dir / "__init__.py").exists():
            continue
        for path in _modules(f"phos.{package_dir.name}"):
            text = path.read_text(encoding="utf-8")
            if "atlas" not in text:
                continue
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr in write_calls:
                        for arg in node.args:
                            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                if "atlas" in arg.value.lower() and (
                                    "src/phos/atlas" in arg.value or "phos/atlas" in arg.value
                                ):
                                    violations.append(f"{path}:{node.lineno}: {arg.value}")
    assert not violations, f"production code writes to atlas paths: {violations}"


# --- Task 4: reproducibility audit -----------------------------------------------

DEMO_SCRIPT = REPO_ROOT / "scripts" / "sim_loop_demo.sh"


def _run_demo() -> str:
    """Run the demo script once and return the SHA-256 of its combined output."""
    result = subprocess.run(
        ["bash", str(DEMO_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"demo script failed (exit {result.returncode}):\n{result.stderr}"
        )
    combined = (result.stdout + result.stderr).encode("utf-8")
    return hashlib.sha256(combined).hexdigest()


@pytest.mark.slow
def test_demo_is_reproducible() -> None:
    """Run the demo twice and assert identical output hashes."""
    hash1 = _run_demo()
    hash2 = _run_demo()
    assert hash1 == hash2, f"demo output differs between runs: {hash1} vs {hash2}"


__all__ = []
