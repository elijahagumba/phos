"""Shared fixtures for the FORGE tests.

Every test that needs a repository gets a real one, made fresh, rather than a mock. The properties
worth testing here are filesystem and git properties: an atomic write, a worktree outside a
checkout, a lock held against a second writer. A mock would assert that the code calls the thing it
calls, which is not the question.

The repository fixture copies the two rule files the red-line guard derives its tokens from, so the
guard is exercised against the real rule and the real resolver rather than a stub list.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

#: The files a throwaway repository needs so the FORGE modules that read rules find them.
_COPIED = (
    "docs/rules/data-tiers.md",
    "docs/method/red-sealed-manifest.txt",
    "data/registry.json",
    "pyproject.toml",
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture()
def repo(tmp_path: Path) -> Iterator[Path]:
    """Yield a small, real git repository laid out like the PHOS checkout.

    The rule files are copied rather than written, so a change to the tier rule changes what the
    red-line guard refuses and the test sees it. The corpus registry is copied for the same reason.

    Args:
        tmp_path: pytest's temporary directory.

    Yields:
        The repository root.
    """
    source = Path(__file__).resolve().parents[2]
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "forge@example.invalid")
    _git(root, "config", "user.name", "FORGE tests")
    _git(root, "config", "commit.gpgsign", "false")

    for relative in _COPIED:
        origin = source / relative
        if not origin.is_file():
            continue
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, destination)

    (root / "src/phos").mkdir(parents=True, exist_ok=True)
    (root / "src/phos/__init__.py").write_text("")
    (root / "README.md").write_text("# throwaway\n")
    (root / ".gitignore").write_text("data/\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "initial")
    yield root


@pytest.fixture()
def declared_repo(repo: Path) -> Iterator[Path]:
    """Yield a repository that also holds one committed declaration in phase ``declared``.

    The record's shape is taken from a real one in this repository rather than hand-written, so
    the fixture cannot drift from the schema. Only the ids, the corpus and the command are
    replaced, which is what makes it a throwaway record rather than a copy of a real result.

    Args:
        repo: The throwaway repository.

    Yields:
        The repository root, with ``E-0001`` committed.
    """
    import json

    source = Path(__file__).resolve().parents[2] / "docs/genesis/experiments/E-0009.json"
    question_source = Path(__file__).resolve().parents[2] / "docs/genesis/questions/Q-0007.json"
    if not source.is_file() or not question_source.is_file():
        pytest.skip("the real records this fixture borrows its shape from are not in this checkout")
    template = json.loads(source.read_text(encoding="utf-8"))
    question_template = json.loads(question_source.read_text(encoding="utf-8"))

    questions = repo / "docs/genesis/questions"
    questions.mkdir(parents=True, exist_ok=True)
    question = dict(question_template)
    question.update(
        {
            "id": "Q-0001",
            "title": "a throwaway question",
            "opened": "2026-11-25",
            "experiments": ["E-0001"],
        }
    )
    (questions / "Q-0001.json").write_text(json.dumps(question, indent=2, sort_keys=True) + "\n")

    declared_block: dict[str, object] = dict(template["declared"])
    declared_block.update(
        {
            "command": "uv run python scripts/lane_probe.py --corpus data/phos-icssim-dev4-walk",
            "corpus": "phos-icssim-dev4-walk",
            "tier": "iterate",
            "result_name": "probe",
            "date": "2026-11-25",
            "challenger_sha256": "0" * 64,
            "bars": [
                {
                    "id": "b1",
                    "metric": "m",
                    "comparator": ">=",
                    "threshold": 1.0,
                    "text": "at least one",
                }
            ],
        }
    )
    record: dict[str, object] = {
        "id": "E-0001",
        "question": "Q-0001",
        "phase": "declared",
        "declared": declared_block,
    }
    directory = repo / "docs/genesis/experiments"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "E-0001.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")

    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "declare E-0001")
    yield repo


@pytest.fixture()
def bare_remote(tmp_path: Path) -> Path:
    """Yield an empty bare repository, to stand in for a push target.

    Args:
        tmp_path: pytest's temporary directory.

    Yields:
        The bare repository's path.
    """
    destination = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(destination)],
        capture_output=True,
        text=True,
        check=True,
    )
    return destination
