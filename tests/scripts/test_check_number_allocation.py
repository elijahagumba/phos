"""A number another branch already used for a different file is refused (ADR 0292)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.check_number_allocation import (
    find_collisions,
    identity,
    main,
    paths_from_name_status,
)


def test_an_adr_and_a_note_are_numbered_and_the_index_is_not() -> None:
    assert identity("docs/adr/0292-the-check.md") == (
        "adr",
        "0292",
        "0292-the-check.md",
    )
    assert identity("easy to reads/87-two-branches-one-number.md") == (
        "note",
        "87",
        "87-two-branches-one-number.md",
    )
    assert identity("docs/adr/README.md") is None


def test_a_rename_contributes_the_new_path_and_an_add_contributes_its_own() -> None:
    blob = "A\0docs/adr/0292-the-check.md\0R100\0docs/adr/0268-old.md\0docs/adr/0289-new.md\0"
    assert paths_from_name_status(blob) == [
        "docs/adr/0292-the-check.md",
        "docs/adr/0289-new.md",
    ]


def test_the_same_filename_on_another_branch_is_one_record() -> None:
    introduced = ["docs/adr/0292-the-check.md"]
    present = {("adr", "0292"): {"0292-the-check.md"}}
    assert find_collisions(introduced, present) == []


def test_a_different_file_under_the_same_number_is_refused() -> None:
    introduced = ["docs/adr/0268-something-else.md"]
    present = {("adr", "0268"): {"0268-the-a7-regeneration-is-declared.md"}}
    found = find_collisions(introduced, present)
    assert len(found) == 1
    assert found[0].number == "0268"
    assert "0268-the-a7-regeneration-is-declared.md" in found[0].also


def test_the_resolved_pair_is_not_reopened_when_the_new_name_is_what_was_added() -> None:
    """ADR 0291 kept 0268 for A7 and moved the other decision to 0289.

    A change that adds the new name must not be failed because some unmerged branch
    still holds the old name under 0268.
    """
    introduced = ["docs/adr/0289-the-build-record-reaches-the-public-tree.md"]
    present = {
        ("adr", "0268"): {
            "0268-the-a7-regeneration-is-declared.md",
            "0268-the-build-record-reaches-the-public-tree.md",
        },
        ("adr", "0289"): {"0289-the-build-record-reaches-the-public-tree.md"},
    }
    assert find_collisions(introduced, present) == []


def test_a_third_name_under_note_70_is_refused() -> None:
    present = {
        ("note", "70"): {
            "70-the-sealed-years-and-a-confidence-test.md",
            "70-quiet-on-years-it-never-saw.md",
        }
    }
    found = find_collisions(["easy to reads/70-a-third.md"], present)
    assert len(found) == 1
    assert set(found[0].also) == present[("note", "70")]


def test_two_new_files_in_one_change_collide_with_each_other() -> None:
    introduced = ["docs/adr/0292-alpha.md", "docs/adr/0292-beta.md"]
    found = find_collisions(introduced, {})
    assert {item.basename for item in found} == {
        "0292-alpha.md",
        "0292-beta.md",
    }


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=number-check@example.com", "-c", "user.name=number-check", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def test_two_branches_taking_one_number_fail_and_the_same_file_does_not(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "README.md").write_text("root\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "root")

    _git(repo, "checkout", "-b", "session-a")
    (repo / "docs" / "adr").mkdir(parents=True)
    (repo / "docs" / "adr" / "0001-alpha.md").write_text("alpha\n", encoding="utf-8")
    _git(repo, "add", "docs/adr/0001-alpha.md")
    _git(repo, "commit", "-m", "alpha")

    _git(repo, "checkout", "main")
    _git(repo, "checkout", "-b", "session-b")
    (repo / "docs" / "adr").mkdir(parents=True)
    (repo / "docs" / "adr" / "0001-beta.md").write_text("beta\n", encoding="utf-8")
    _git(repo, "add", "docs/adr/0001-beta.md")
    _git(repo, "commit", "-m", "beta")

    refused = main(["--from", "main", "--to", "session-b"], repo=repo)
    assert refused == 1

    _git(repo, "checkout", "main")
    _git(repo, "checkout", "-b", "session-c")
    (repo / "docs" / "adr").mkdir(parents=True)
    (repo / "docs" / "adr" / "0002-same.md").write_text("same\n", encoding="utf-8")
    _git(repo, "add", "docs/adr/0002-same.md")
    _git(repo, "commit", "-m", "same, first branch")

    _git(repo, "checkout", "main")
    _git(repo, "checkout", "-b", "session-d")
    (repo / "docs" / "adr").mkdir(parents=True, exist_ok=True)
    (repo / "docs" / "adr" / "0002-same.md").write_text("same again\n", encoding="utf-8")
    _git(repo, "add", "docs/adr/0002-same.md")
    _git(repo, "commit", "-m", "the same record")
    assert main(["--from", "main", "--to", "session-d"], repo=repo) == 0
