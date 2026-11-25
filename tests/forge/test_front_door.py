"""Tests for the front door: `/forge`, `/forge-status` and `/forge-resume`.

The two the task names are here:

* ``/forge`` with an empty goal refuses.
* ``/forge`` refuses from a checkout where the hooks are not loaded.

The second is tested two ways, because "the hooks are not loaded" has two causes that need different
answers. The hook **files** can be absent from the checkout, which the preflight can see. Or the
editor's window can be open on a parent directory, which nothing inside the repository can see, and
which the command file has to say out loud. The first is a test; the second is a test that the
command text says it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from phos.forge import conductor, preflight

ROOT = Path(__file__).resolve().parents[2]
COMMANDS = ROOT / ".claude/commands"
CURSOR_COMMANDS = ROOT / ".cursor/commands"


def _forge(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run one FORGE subcommand against a repository.

    Args:
        root: The repository root the command should treat as its own.
        *args: The subcommand and its flags.

    Returns:
        The completed process.
    """
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "forge.py"), *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "PYTHONPATH": f"{ROOT / 'src'}"},
    )


@pytest.fixture()
def clean_repo(repo: Path) -> Path:
    """Return a throwaway repository that passes the whole preflight.

    The shared ``repo`` fixture copies the tier rule, the manifest and the registry but not the
    execution-master rule, and it has no remote. Both are deliberate there and wrong here: the point
    of this fixture is a checkout where every check passes, so that a test about the *next* refusal
    is not blocked by an earlier one.

    Args:
        repo: The throwaway repository.

    Returns:
        The repository root, with hooks, the execution rule and a PHOS Labs remote.
    """
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude/settings.json").write_text('{"hooks": {}}\n')
    (repo / ".cursor").mkdir(exist_ok=True)
    (repo / ".cursor/hooks.json").write_text('{"version": 1, "hooks": {}}\n')

    execution = repo / "docs/rules/phos-execution-master.md"
    execution.parent.mkdir(parents=True, exist_ok=True)
    if not execution.is_file():
        execution.write_text("# the lock, copied only so the gate check can find it\n")

    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "remote",
            "add",
            "origin",
            "https://github.com/elijahagumba/phoslabs.git",
        ],
        capture_output=True,
        check=True,
    )
    subprocess.run(["git", "-C", str(repo), "add", "-A"], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "add hooks and a remote"],
        capture_output=True,
        check=True,
    )
    return repo


# -- the two tests the task names --------------------------------------------------------------


@pytest.mark.parametrize("goal", ["", "   ", "\n\t "])
def test_forge_with_an_empty_goal_refuses(clean_repo: Path, goal: str) -> None:
    """An empty goal is refused, and nothing is created.

    The refusal has to come before the preflight and before any worktree, because a front door that
    opens on nothing and then invents a goal is worse than one that stays shut.
    """
    done = _forge(clean_repo, "forge", goal)
    assert done.returncode == 2
    assert "the goal is empty" in done.stderr
    assert not (clean_repo / "docs/forge/state").exists(), "nothing may be written"


def test_forge_refuses_where_the_hook_configuration_is_absent(repo: Path) -> None:
    """A checkout without the hook files has no guards, so FORGE does not run there.

    ADR 0417 and ADR 0419 are the reason this is a refusal: a checkout whose hooks are not loaded
    can read a red corpus with nothing warning about it, and FORGE would then be the only gate in a
    repository whose whole method assumes several.
    """
    assert not (repo / ".cursor/hooks.json").exists()

    checked = preflight.run(repo)
    assert not checked.passed
    names = {check.name for check in checked.failures}
    assert "hooks present" in names

    done = _forge(repo, "forge", "measure something on the development corpus")
    assert done.returncode == 2
    assert "hooks present" in done.stdout + done.stderr
    assert not (repo / "docs/forge/state").exists(), "a refused preflight creates nothing"


def test_forge_refuses_when_the_claude_hook_configuration_is_absent(clean_repo: Path) -> None:
    """The other half: a checkout with Cursor hooks and no Claude Code hooks is still refused."""
    (clean_repo / ".claude/settings.json").unlink()
    subprocess.run(
        ["git", "-C", str(clean_repo), "commit", "-am", "drop the claude hooks"],
        capture_output=True,
        check=True,
    )
    done = _forge(clean_repo, "forge", "measure something")
    assert done.returncode == 2
    assert ".claude/settings.json" in done.stdout + done.stderr


def test_forge_refuses_when_the_hook_configuration_will_not_parse(clean_repo: Path) -> None:
    """A hook file that is present and broken is worse than an absent one: it looks loaded."""
    (clean_repo / ".cursor/hooks.json").write_text("{not json")
    subprocess.run(
        ["git", "-C", str(clean_repo), "commit", "-am", "break the hooks"],
        capture_output=True,
        check=True,
    )
    done = _forge(clean_repo, "forge", "measure something")
    assert done.returncode == 2
    assert "will not parse" in done.stdout + done.stderr


# -- the conductor refuses before it sizes anything -------------------------------------------


def test_an_empty_goal_is_refused_by_the_conductor_itself(clean_repo: Path) -> None:
    outcome = conductor.conduct(clean_repo, "  ")
    assert outcome.blocked
    assert "the goal is empty" in outcome.blocked
    assert not outcome.ok


def test_a_dirty_tree_is_refused(clean_repo: Path) -> None:
    (clean_repo / "somebody-elses-work.md").write_text("half finished\n")
    outcome = conductor.conduct(clean_repo, "measure the walk question")
    assert outcome.blocked
    assert outcome.preflight is not None
    assert "clean main" in outcome.blocked
    assert not (clean_repo / "docs/forge/state").exists()


def test_a_foreign_remote_is_refused(repo: Path) -> None:
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude/settings.json").write_text('{"hooks": {}}\n')
    (repo / ".cursor").mkdir(exist_ok=True)
    (repo / ".cursor/hooks.json").write_text('{"version": 1, "hooks": {}}\n')
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin", "https://example.invalid/x.git"],
        capture_output=True,
        check=True,
    )
    subprocess.run(["git", "-C", str(repo), "add", "-A"], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "hooks"], capture_output=True, check=True
    )
    checked = preflight.run(repo)
    assert "remote" in {check.name for check in checked.failures}


def test_a_never_tier_corpus_is_refused(clean_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outcome = conductor.conduct(clean_repo, "measure something", corpus="hai")
    assert outcome.blocked
    assert "cannot be used" in outcome.blocked


# -- the conductor sizes a team by a rule a reader can argue with -------------------------------


@pytest.mark.parametrize(
    ("goal", "shape"),
    [
        ("measure whether the sequential column catches the walks", "research"),
        ("build an adapter for the DNP3 lane", "engineering"),
        ("decide the scope of the next programme", "institutional"),
        ("something that matches no word at all", "research"),
    ],
)
def test_a_goal_is_classified_by_its_shape(goal: str, shape: str) -> None:
    assert conductor.classify(goal) == shape


def test_a_research_team_has_four_roles_and_the_analyst() -> None:
    team = conductor.size_team("measure the walk question")
    assert "principal_research_scientist" in team.roles
    assert "applied_scientist" in team.roles
    assert "verification_engineer" in team.roles
    assert "institutional_analyst" in team.roles
    assert len(team.roles) == 5


def test_an_engineering_team_includes_the_adversary() -> None:
    team = conductor.size_team("build the adapter")
    assert "adversarial_researcher" in team.roles
    assert "principal_architect" in team.roles
    assert "principal_engineer" in team.roles


def test_the_analyst_is_always_on() -> None:
    for goal in ("measure it", "build it", "decide it"):
        assert "institutional_analyst" in conductor.size_team(goal).roles


def test_a_team_has_no_duplicate_roles() -> None:
    team = conductor.size_team("build and measure the adapter")
    assert len(team.roles) == len(set(team.roles))


def test_the_team_size_rule_says_it_is_fixed_until_the_baseline_exists() -> None:
    team = conductor.size_team("measure the walk question")
    assert "fixed by shape" in team.reason
    assert "baseline" in team.reason


def test_where_results_are_names_the_four_paths() -> None:
    paths = conductor.where_results_are(ROOT, "an-operation")
    assert "docs/forge/state/an-operation.json" in paths.values()
    assert "docs/genesis/experiments/" in paths.values()
    assert "docs/method/INBOX.md" in paths.values()


# -- the command files exist in both editors and carry the required behaviour --------------------


@pytest.mark.parametrize("name", ["forge.md", "forge-status.md", "forge-resume.md"])
def test_the_claude_command_exists(name: str) -> None:
    assert (COMMANDS / name).is_file()


@pytest.mark.parametrize("name", ["forge.md", "forge-status.md", "forge-resume.md"])
def test_the_cursor_entry_point_exists_and_points_at_the_claude_one(name: str) -> None:
    path = CURSOR_COMMANDS / name
    assert path.is_file()
    text = path.read_text()
    assert f".claude/commands/{name}" in text
    assert "third-party extensibility" in text


def test_the_forge_command_carries_the_five_required_behaviours() -> None:
    """The command text must do the five things the task lists, and say where the results go."""
    text = (COMMANDS / "forge.md").read_text()

    assert "$ARGUMENTS" in text, "it reads the goal"
    assert "preflight" in text, "it runs the preflight"
    assert "conductor" in text, "it hands the goal to the conductor"
    assert "size_team" in text or "Size the team" in text, "the conductor sizes the team"
    assert "worktree" in text.lower(), "the conductor creates worktrees"
    assert "gate (a)" in text.lower() and "gate (b)" in text.lower() and "gate (c)" in text.lower()
    assert "any output that names a red or sealed path" in text.lower(), "it stops on the abort"
    assert "docs/method/INBOX.md" in text
    assert "where the results are" in text.lower()


def test_the_forge_command_says_what_to_do_when_the_conductor_is_missing() -> None:
    text = (COMMANDS / "forge.md").read_text()
    assert "cannot be reached" in text
    assert "do nothing else" in text


def test_the_forge_command_refuses_an_empty_goal() -> None:
    text = (COMMANDS / "forge.md").read_text()
    # The sentence wraps, so match on the normalised text rather than a line.
    flat = " ".join(text.split())
    assert "stop immediately" in flat.lower()
    assert "empty" in flat.lower()
    assert "Do not infer a goal" in flat


def test_the_forge_command_never_mounts_the_sealed_volume() -> None:
    text = (COMMANDS / "forge.md").read_text()
    assert "Never mount it" in text
    assert "password" in text


def test_the_status_command_reads_the_state_files() -> None:
    text = (COMMANDS / "forge-status.md").read_text()
    assert "docs/forge/state/" in text
    assert "forge.py operations" in text
    assert "forge.py status" in text


def test_the_resume_command_needs_an_id_and_refuses_a_terminal_operation() -> None:
    text = (COMMANDS / "forge-resume.md").read_text()
    assert "stop" in text.lower()
    assert "COMPLETED" in text
    assert "REJECTED" in text
    assert "does not restart" in text


def test_the_resume_command_does_not_make_fresh_worktrees() -> None:
    """A resume that makes new worktrees loses the work in the old ones."""
    text = (COMMANDS / "forge-resume.md").read_text()
    assert "Do not create new ones" in text


# -- the CLI behind the commands ----------------------------------------------------------------


def test_the_preflight_subcommand_reports_every_check(clean_repo: Path) -> None:
    done = _forge(clean_repo, "preflight")
    for name in (
        "clean main",
        "no clashing worktrees",
        "number allocation",
        "gates present",
        "hooks present",
        "remote",
    ):
        assert name in done.stdout


def test_the_operations_subcommand_lists_from_the_state_directory(clean_repo: Path) -> None:
    done = _forge(clean_repo, "operations")
    assert done.returncode == 0
    assert "no operations" in done.stdout


def test_number_allocation_computes_from_the_files(clean_repo: Path) -> None:
    numbers = preflight.next_numbers(clean_repo)
    assert numbers["experiments"] == 1
    assert numbers["questions"] == 1

    directory = clean_repo / "docs/genesis/experiments"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "E-0007.json").write_text("{}\n")
    assert preflight.next_numbers(clean_repo)["experiments"] == 8


# -- nothing here restates a procedure ----------------------------------------------------------


def test_the_cursor_entry_points_do_not_restate_the_procedure() -> None:
    """A second copy of a procedure is the drift this repository's rules exist to prevent."""
    for name in ("forge.md", "forge-status.md", "forge-resume.md"):
        text = (CURSOR_COMMANDS / name).read_text()
        assert "Read `.claude/commands/" in text
        assert len(text.splitlines()) < 40, f"{name} is becoming a second copy"


def test_every_script_the_commands_name_exists_and_is_tracked() -> None:
    """A command file that names a script the checkout does not carry is a front door onto nothing.

    This is not hypothetical. ``scripts/forge.py`` was written to the working tree and left out of
    the commit twice, so the pushed branch carried all three commands pointing at a file that was
    not there. Nothing caught it, because the tests read the command text and ran the script from
    the working tree: the same file in one place and not the other. So this checks both, and it
    checks
    git rather than the filesystem, because the filesystem is what was right.
    """
    import re

    referenced: set[str] = set()
    for name in ("forge.md", "forge-status.md", "forge-resume.md"):
        text = (COMMANDS / name).read_text()
        referenced |= set(re.findall(r"scripts/[\w./-]+\.py", text))

    assert referenced, "the commands must name at least one script, or this test proves nothing"

    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "scripts"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    for relative in sorted(referenced):
        assert (ROOT / relative).is_file(), f"{relative} is named by a command and absent"
        assert relative in tracked, f"{relative} is named by a command and not tracked by git"


def test_every_forge_script_is_tracked() -> None:
    """The scripts behind FORGE are all in git, not only on this machine."""
    import subprocess as sp

    tracked = set(
        sp.run(
            ["git", "-C", str(ROOT), "ls-files", "scripts"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
    )
    for relative in ("scripts/forge.py", "scripts/forge_baseline.py", "scripts/forge_atlas.py"):
        assert (ROOT / relative).is_file(), f"{relative} is absent"
        assert relative in tracked, f"{relative} is not tracked by git"
