"""Tests for the three human approval gates.

Gate (b) is tested twice over: once by behaviour (a missing volume is refused, a present one is
accepted) and once by reading the module's own source, because the prohibition that matters is that
FORGE never mounts the image and never reads a password. A behavioural test cannot prove the absence
of an attempt that only happens on a machine where the volume is missing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from phos.forge import gates
from phos.forge.gates import (
    ALLOWED_REMOTE,
    GateOutcome,
    require_committed_declaration,
    require_landing_push,
    require_landing_target,
    require_not_main,
    require_sealed_volume,
)

GATES_SOURCE = Path(__file__).resolve().parents[2] / "src/phos/forge/gates.py"


# -- gate (a): the declaration is committed before any build ---------------------------------


def test_a_committed_declaration_passes(declared_repo: Path) -> None:
    outcome = require_committed_declaration(declared_repo, "E-0001")
    assert outcome.passed
    assert outcome.gate == "a"


def test_a_missing_declaration_is_refused_and_named(repo: Path) -> None:
    outcome = require_committed_declaration(repo, "E-0001")
    assert not outcome.passed
    assert "not committed at HEAD" in outcome.detail
    assert outcome.missing == ("docs/genesis/experiments/E-0001.json",)


def test_an_uncommitted_declaration_is_refused(declared_repo: Path) -> None:
    """The distinction the gate exists for: a bar in a working tree is not a bar."""
    path = declared_repo / "docs/genesis/experiments/E-0002.json"
    path.write_text('{"id": "E-0002", "phase": "declared"}')
    outcome = require_committed_declaration(declared_repo, "E-0002")
    assert not outcome.passed
    assert "not committed at HEAD" in outcome.detail


def test_a_declaration_edited_after_the_commit_is_refused(declared_repo: Path) -> None:
    path = declared_repo / "docs/genesis/experiments/E-0001.json"
    text = path.read_text()
    path.write_text(text.replace('"threshold": 1.0', '"threshold": 2.0'))
    outcome = require_committed_declaration(declared_repo, "E-0001")
    assert not outcome.passed
    assert "differs from HEAD" in outcome.detail


@pytest.mark.parametrize("phase", ["measured", "judged"])
def test_a_record_past_declared_phase_is_refused(declared_repo: Path, phase: str) -> None:
    path = declared_repo / "docs/genesis/experiments/E-0001.json"
    text = path.read_text().replace('"phase": "declared"', f'"phase": "{phase}"')
    path.write_text(text)
    import subprocess

    subprocess.run(
        ["git", "-C", str(declared_repo), "commit", "-am", f"move to {phase}"],
        capture_output=True,
        check=True,
    )
    outcome = require_committed_declaration(declared_repo, "E-0001")
    assert not outcome.passed
    assert phase in outcome.detail


def test_a_declaration_not_on_the_builders_base_is_refused(
    declared_repo: Path, repo: Path
) -> None:
    """A branch that does not carry the declaration has nothing to be judged against."""
    import subprocess

    before = subprocess.run(
        ["git", "-C", str(declared_repo), "rev-parse", "HEAD~1"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    outcome = require_committed_declaration(declared_repo, "E-0001", base_commit=before)
    assert not outcome.passed
    assert "not an ancestor" in outcome.detail


def test_a_declaration_on_the_base_passes_the_ancestry_check(declared_repo: Path) -> None:
    import subprocess

    head = subprocess.run(
        ["git", "-C", str(declared_repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    outcome = require_committed_declaration(declared_repo, "E-0001", base_commit=head)
    assert outcome.passed


def test_a_record_with_no_phase_is_refused(declared_repo: Path) -> None:
    path = declared_repo / "docs/genesis/experiments/E-0001.json"
    path.write_text(path.read_text().replace('"phase": "declared",', ""))
    import subprocess

    subprocess.run(
        ["git", "-C", str(declared_repo), "commit", "-am", "drop the phase"],
        capture_output=True,
        check=True,
    )
    outcome = require_committed_declaration(declared_repo, "E-0001")
    assert not outcome.passed
    assert "does not state a phase" in outcome.detail


# -- gate (b): the sealed referee step stops unless the volume is mounted ---------------------


def test_a_missing_volume_is_refused_and_names_what_is_missing(tmp_path: Path) -> None:
    absent = tmp_path / "not-mounted"
    outcome = require_sealed_volume(absent)
    assert not outcome.passed
    assert outcome.gate == "b"
    assert outcome.missing == (str(absent),)
    assert "does not run" in outcome.detail


def test_a_present_volume_passes(tmp_path: Path) -> None:
    mounted = tmp_path / "PHOSRED"
    mounted.mkdir()
    outcome = require_sealed_volume(mounted)
    assert outcome.passed


def test_the_refusal_says_forge_will_not_mount_it(tmp_path: Path) -> None:
    outcome = require_sealed_volume(tmp_path / "absent")
    assert "does not mount" in outcome.detail
    assert "password" in outcome.detail


def test_the_gates_module_never_mounts_and_never_reads_a_password() -> None:
    """The prohibition the gate rests on, checked against the code rather than promised.

    These words appearing in executable code would mean FORGE had acquired the ability to open the
    vault, which is a human's step and a human's password. The module's prose *names* them, on
    purpose, to say what it does not do. So the check parses the module and looks only at the
    strings and names that are not docstrings: a comment saying "we never call hdiutil" is the
    opposite of a call to it, and a test that could not tell the two apart would push the
    explanation out of the file.
    """
    import ast

    tree = ast.parse(GATES_SOURCE.read_text(encoding="utf-8"))

    # Docstrings are found by node identity, not by comparing text: ast.get_docstring normalises
    # the string it returns, so a text comparison misses the node that holds it.
    docstring_nodes: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstring_nodes.add(id(body[0].value))

    executed: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstring_nodes:
                executed.append(node.value)
        elif isinstance(node, ast.Name):
            executed.append(node.id)
        elif isinstance(node, ast.Attribute):
            executed.append(node.attr)
        elif isinstance(node, ast.alias):
            executed.append(node.name)
            if node.asname:
                executed.append(node.asname)
        elif isinstance(node, ast.arg):
            executed.append(node.arg)

    for forbidden in ("hdiutil", "attach", "keychain", "getpass", "osascript", "security"):
        hits = [item for item in executed if forbidden in item]
        assert not hits, f"{forbidden} appears in executable code: {hits}"


def test_the_gates_module_imports_nothing_that_could_mount_a_volume() -> None:
    text = GATES_SOURCE.read_text(encoding="utf-8")
    imports = re.findall(r"^\s*(?:from|import)\s+([\w.]+)", text, re.MULTILINE)
    assert "subprocess" in imports, "the module should use git, so this test is looking at it"
    assert "shutil" not in imports
    assert "getpass" not in imports
    assert "keyring" not in imports


# -- gate (c): nothing merges to main ----------------------------------------------------------


@pytest.mark.parametrize("branch", ["main", "master"])
def test_a_protected_branch_cannot_be_a_work_branch(branch: str) -> None:
    outcome = require_not_main(branch)
    assert not outcome.passed
    assert outcome.gate == "c"


@pytest.mark.parametrize("branch", ["forge/v0", "forge/op1/builder_a", "method/week-02-a"])
def test_an_ordinary_branch_is_accepted(branch: str) -> None:
    assert require_not_main(branch).passed


def test_an_empty_branch_is_refused() -> None:
    assert not require_not_main("").passed


def test_the_phoslabs_remote_is_accepted() -> None:
    assert require_landing_target(f"https://github.com/{ALLOWED_REMOTE}.git").passed
    assert require_landing_target(f"git@github.com:{ALLOWED_REMOTE}.git").passed


def test_another_remote_is_refused() -> None:
    outcome = require_landing_target("https://github.com/someone/phos.git")
    assert not outcome.passed
    assert "public repository" in outcome.detail


def test_an_empty_remote_is_refused() -> None:
    assert not require_landing_target("").passed


def test_a_push_to_main_is_refused() -> None:
    outcome = require_landing_push(
        f"https://github.com/{ALLOWED_REMOTE}.git", "refs/heads/forge/v0:refs/heads/main"
    )
    assert not outcome.passed
    assert "does not push to main" in outcome.detail


def test_a_push_to_a_working_branch_is_accepted() -> None:
    outcome = require_landing_push(
        f"https://github.com/{ALLOWED_REMOTE}.git", "refs/heads/forge/v0:refs/heads/forge/v0"
    )
    assert outcome.passed


def test_a_push_to_main_at_a_foreign_remote_names_the_remote_first() -> None:
    """The remote check dominates, because pushing to the wrong place is the worse mistake."""
    outcome = require_landing_push("https://example.invalid/x.git", "x:main")
    assert not outcome.passed
    assert "PHOS Labs" in outcome.detail


def test_a_gate_outcome_is_truthy_only_when_it_passed() -> None:
    assert GateOutcome("a", True, "fine")
    assert not GateOutcome("a", False, "no")


def test_the_allowed_remote_is_the_labs_one() -> None:
    assert ALLOWED_REMOTE == "elijahagumba/phoslabs"


def test_the_public_repository_is_not_named_anywhere_in_the_package() -> None:
    """The public ``phos`` repository is never a target, so no module names it."""
    package = GATES_SOURCE.parent
    for path in package.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "elijahagumba/phos.git" not in text, f"{path.name} names the public repository"


def test_the_sealed_volume_is_the_one_the_record_names() -> None:
    assert gates.SEALED_VOLUME == Path("/Volumes/PHOSRED")
