"""Tests for worktree creation, scope, conflict detection and removal.

Each test makes a real repository and a real worktree, because the properties under test are git's
and the filesystem's: a worktree outside the checkout, a branch that is not ``main``, two roles
touching one file.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from phos.forge import worktree
from phos.forge.worktree import (
    Worktree,
    WorktreeError,
    changed_files,
    create,
    default_path,
    detect_file_conflicts,
    head_commit,
    is_outside_checkout,
    prune,
    remove,
)


def test_default_path_is_beside_the_repository(repo: Path) -> None:
    path = default_path(repo, "op-1", "builder_a")
    assert path.is_absolute()
    assert is_outside_checkout(repo, path)
    assert is_outside_checkout(repo, path)
    assert path.parts[-3:] == ("op-1", "builder_a") or "op-1" in path.parts


def test_a_worktree_is_created_outside_the_checkout(repo: Path) -> None:
    made = create(repo, operation="op-1", role="builder_a", branch="forge/op-1-a")
    assert made.path.exists()
    assert is_outside_checkout(repo, made.path)
    assert made.branch == "forge/op-1-a"
    assert made.base_commit == head_commit(repo)
    remove(made, force=True)
    prune(repo)


def test_the_main_checkout_is_not_disturbed(repo: Path) -> None:
    before = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    made = create(repo, operation="op-1", role="builder_a", branch="forge/op-1-a")
    after = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert before == after
    remove(made, force=True)


def test_main_is_refused_as_a_branch(repo: Path) -> None:
    with pytest.raises(WorktreeError, match="not a place to work"):
        create(repo, operation="op-1", role="x", branch="main")


def test_a_path_inside_the_checkout_is_refused(repo: Path) -> None:
    with pytest.raises(WorktreeError, match="inside"):
        create(repo, operation="op-1", role="x", branch="forge/x", path=repo / "inside")


def test_an_existing_path_is_refused(repo: Path) -> None:
    existing = repo.parent / "already-there"
    existing.mkdir()
    with pytest.raises(WorktreeError, match="already exists"):
        create(repo, operation="op-1", role="x", branch="forge/x", path=existing)


def test_an_existing_branch_is_refused(repo: Path) -> None:
    made = create(repo, operation="op-1", role="builder_a", branch="forge/op-1-a")
    remove(made, force=True)
    # The branch survives the worktree's removal, which is the point: a stopped role's work is kept.
    with pytest.raises(WorktreeError, match="already exists"):
        create(repo, operation="op-1", role="builder_a", branch="forge/op-1-a")


def test_changed_files_sees_edits_and_new_files(repo: Path) -> None:
    made = create(repo, operation="op-1", role="builder_a", branch="forge/op-1-a")
    (made.path / "README.md").write_text("# changed\n")
    (made.path / "new.txt").write_text("new\n")
    found = changed_files(made)
    assert "README.md" in found
    assert "new.txt" in found
    remove(made, force=True)


def test_two_roles_touching_one_file_is_reported(repo: Path) -> None:
    first = create(repo, operation="op-1", role="builder_a", branch="forge/op-1-a")
    second = create(repo, operation="op-1", role="builder_b", branch="forge/op-1-b")
    (first.path / "shared.txt").write_text("a\n")
    (second.path / "shared.txt").write_text("b\n")
    conflicts = detect_file_conflicts([first, second])
    assert "shared.txt" in conflicts
    assert set(conflicts["shared.txt"]) == {"builder_a", "builder_b"}
    remove(first, force=True)
    remove(second, force=True)


def test_two_roles_touching_different_files_is_not_a_conflict(repo: Path) -> None:
    first = create(repo, operation="op-1", role="builder_a", branch="forge/op-1-a")
    second = create(repo, operation="op-1", role="builder_b", branch="forge/op-1-b")
    (first.path / "a.txt").write_text("a\n")
    (second.path / "b.txt").write_text("b\n")
    assert detect_file_conflicts([first, second]) == {}
    remove(first, force=True)
    remove(second, force=True)


def test_removal_refuses_uncommitted_work_without_force(repo: Path) -> None:
    made = create(repo, operation="op-1", role="builder_a", branch="forge/op-1-a")
    (made.path / "work.txt").write_text("uncommitted\n")
    with pytest.raises(WorktreeError, match="git worktree remove failed"):
        remove(made)
    assert made.path.exists(), "a refused removal must not take the work with it"
    remove(made, force=True)


def test_removal_locates_the_main_checkout_from_gits_own_answer(repo: Path) -> None:
    """``--git-common-dir`` is absolute on this git, which an earlier draft mishandled."""
    made = create(repo, operation="op-1", role="builder_a", branch="forge/op-1-a")
    common = subprocess.run(
        ["git", "-C", str(made.path), "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert Path(common).is_absolute() or Path(common).exists()
    remove(made, force=True)
    assert not made.path.exists()


def test_head_commit_refuses_an_unknown_ref(repo: Path) -> None:
    with pytest.raises(WorktreeError):
        head_commit(repo, "no-such-ref")


def test_is_outside_checkout_treats_a_sibling_as_outside(repo: Path) -> None:
    assert is_outside_checkout(repo, repo.parent / "sibling")


def test_is_outside_checkout_treats_a_child_as_inside(repo: Path) -> None:
    assert not is_outside_checkout(repo, repo / "child")


def test_a_worktree_carries_the_committed_declaration(declared_repo: Path) -> None:
    """A builder's branch must carry the bar it will be judged against."""
    made = create(declared_repo, operation="op-1", role="builder_a", branch="forge/op-1-a")
    declaration = made.path / "docs/genesis/experiments/E-0001.json"
    assert declaration.is_file()
    remove(made, force=True)


def test_a_worktree_of_an_earlier_commit_does_not_carry_a_later_file(repo: Path) -> None:
    """The baseline harness's property: an agent must not see the answer in its own tree."""
    first = head_commit(repo)
    (repo / "answer.txt").write_text("the result\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "the answer"], capture_output=True, check=True
    )

    made = create(repo, operation="op-1", role="builder_a", branch="forge/op-1-a", base=first)
    assert not (made.path / "answer.txt").exists()
    assert (repo / "answer.txt").exists()
    remove(made, force=True)


def test_which_git_finds_the_binary() -> None:
    assert worktree.which_git() is not None


def test_a_worktree_dataclass_is_frozen() -> None:
    made = Worktree(path=Path("/tmp/x"), branch="b", base_commit="abc", role="r")
    with pytest.raises(AttributeError):
        made.branch = "other"  # type: ignore[misc]
