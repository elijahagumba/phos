# ADR 0440 — The exported suite is green, and a test that passed without checking anything is gone

- **Status:** Accepted
- **Date:** 2026-11-15
- **PART:** public record
- **Supersedes:** nothing
- **Depends on:** [0439](0439-the-public-surfaces-carry-the-custody-argument-and-the-test-programme.md), [0417](0417-the-guards-were-observed-firing-and-only-the-claude-shims-were-loaded.md), [0416](0416-the-corpus-is-resolved-against-the-rule-not-the-payload.md), [0414](0414-the-five-guards-are-functions-and-both-editors-run-them.md), [0092](0092-real-corpus-tests-are-marked-slow.md), [0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md)

## Context

ADR 0439 Decision 8 recorded that the exported suite was red — **36 failed, 6,183 passed, 48
skipped, 45 deselected, 79 errors** — and named the fix as a decision rather than taking it. The
front page tells a reader to run `uv run pytest -q` on a fresh clone, so a red exported suite makes
the page untrue about the one thing a sceptic would check first.

One root cause. `tests/genesis/` and `tests/guards/test_parity.py` read two things the export cannot
carry: `docs/rules/{data-tiers,docs-on-main}.md`, which are symlinks into `.cursor/rules/`, and the
editor hook scripts under `.cursor/` and `.claude/`. All three paths are `[forbidden].paths` in
`public/manifest.toml`, and for good reason — they are the agent rules. The tests arrived with ADRs
0412–0417 and had never been trial-exported, so nothing had looked.

Three options were put: exclude those trees from the export, which lowers the published test count
and removes the guard-parity evidence from the public repository; export the rules and hooks, which
publishes exactly what those forbidden paths exist to protect; or mark the tests `lab_only`, which
`tests/conftest.py` already skips when `public/manifest.toml` is absent. **The third was chosen.**

## Decision 1 — `lab_only` where the unit is a whole module or class, a guard where it is a subset

The marker is the declarative statement and belongs where a reader meets the code. But a marker on a
module skips every test in it, and two of the five files are mixed: of `test_gatehost.py`'s 39 tests,
13 passed in the export and must keep passing. Marking the module would have hidden them.

So the dependency is declared where it actually lives:

- **Module-level `pytestmark = pytest.mark.lab_only`** on `tests/genesis/test_cli.py` (37 tests),
  `test_store.py` (12), `test_store_safety.py` (20) and `tests/guards/test_parity.py` (17). Every
  test in each of these failed in the export, so the marker skips nothing that could have run.
- **Class-level** on `test_gatehost.py`'s `TestCrossEnvironmentParity` (8),
  `TestCursorHooksConfig` (2) and `TestTheGateFindsItsOwnRecord` (3) — the three whose subject *is*
  the editor hook trees.
- **A guard on the two shared helpers**, which covers the subsets without fourteen scattered
  decorators and covers tests written later that nobody remembers to mark: the `repo` fixture in
  `tests/genesis/conftest.py` and `seeded()` in `test_gatehost.py` now call
  `tests.lab_only.skip_if_absent` on the data-tier rule. That is what takes `TestDecide`'s six
  lab-dependent tests while leaving its seventh running, and `TestTierCrossCheck`'s eight.

`tests/lab_only.py` gains `RULES_ABSENT_REASON` and `HOOKS_ABSENT_REASON`, so every skip names the
rule that causes it instead of saying "lab-only" and stopping.

## Decision 2 — One module skips itself, because a marker is applied too late to help it

`tests/genesis/test_tiercheck.py` calls `named_in()` **inside** its `@pytest.mark.parametrize`
decorators, which are evaluated while the module is imported — before
`pytest_collection_modifyitems` runs and before any marker exists to be honoured. In the export that
import raised, took the whole collection down, and produced the two cascading failures in
`tests/eval/test_slow_marker.py`, which shells out to `pytest --collect-only` and asserts a clean
exit.

So that module guards itself with `pytest.skip(..., allow_module_level=True)` on the same condition
the marker expresses, with a comment saying why the marker could not carry it. This is the one place
where the mechanism had to differ from the instruction, and the reason is mechanical rather than a
judgement.

## Decision 3 — A test that passed without checking anything is now a skip, and that is the point

`TestTheGateFindsItsOwnRecord::test_no_cursor_hook_reads_an_undocumented_environment_variable`
iterates `.cursor/hooks/*.py` and asserts that no script reads `CURSOR_PROJECT_DIR`. In the export
that directory does not exist, the glob yields nothing, the loop body never runs, and **the test
passed having checked nothing.** It was green in the red suite, and it would have stayed green
through any of the three options above.

That is this project's own named failure — an empty register checks nothing — occurring in the test
suite rather than on the operator page. It is now marked with the others, and
`HOOKS_ABSENT_REASON` says in the skip message why a vacuous pass is worse than an honest skip. It
is the only test here that was *removed from the passing count* by this change, and finding it is
the strongest argument for having trialled the export at all.

## Decision 4 — The published test count is replaced with a measured one

ADR 0439 left `4,943 tests` on the front page because the exported suite did not pass and quoting a
count for a red suite is worse than quoting an old one. It passes now, so the figure is measured and
replaced: **6,184 tests, about four and a half minutes**, with **162 skipped**, each naming its own
reason.

**How it was measured, because the number is published:** export into a fresh clone of the public
repository, `uv sync`, then `uv run pytest -q`. It is not counted in the lab tree, which collects a
different set — the front page's claim is about what *a reader* gets, so it is measured where a
reader stands. The page now also says the 162 skips exist and why, which the old line did not.

## Consequences

**The exported suite is green: 6,184 passed, 162 skipped, 45 deselected, 0 failed, 0 errors.** The
arithmetic against the red run closes exactly, which is the check that nothing was over-skipped:
passed went 6,183 → 6,184, being the two `test_slow_marker` cascades now passing less the one
vacuous test now skipped; skipped went 48 → 162, being the 36 failures and 79 errors less those two
cascades plus that one vacuous pass. **Every newly skipped test is one that previously failed or
errored, plus the false green.** Nothing that could run was silenced.

**The lab is unchanged**, which is the other half of the requirement. `uv run pytest tests/genesis
tests/guards -q -rs` gives **331 passed, 0 skipped**: the marker is inert here, because
`public/manifest.toml` is present. The full lab suite stays at **6,526 passed, 27 skipped, 45
deselected**.

**What this does not claim.** A green public suite is not a reproduction by an outsider — v1's
criterion for that is still unmet, and nobody outside the project has run anything. It is not a
security audit; `tests/eval/test_offline_core.py` is a source-shape check and says so. And the
guard-parity evidence is now **absent** from the public repository rather than failing there: a
reader cannot see that both editors enforce the same gate, because the scripts that would prove it
are the ones the export forbids. That is the cost of the option taken, and it is stated rather than
discovered.

**No measurement of anything else.** No score, no detector, no corpus opened, no harness run. No
frozen number requoted or moved; v1 stays **8 of 12**. `.phos_roadmap_state.json` untouched, so
`current_session` stays **P1**, the blocked human conversation. **No export to the live repository
was made and nothing was pushed** — the trial was into a throwaway clone, and publishing remains a
separate act.
