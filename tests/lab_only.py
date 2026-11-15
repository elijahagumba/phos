"""Skip a lab pin when the public export did not carry the file."""

from __future__ import annotations

from pathlib import Path

import pytest

ABSENT_REASON = (
    "experiments/ is not an include pattern in public/manifest.toml, so this pin is not in "
    "the public tree. Exporting the small text file is the alternative. In a checkout where "
    "the file is present, a moved byte still fails the pin."
)


#: Why a `.phos_*` tracker is absent. `public/manifest.toml` forbids the pattern outright, so the
#: tracker never reaches the public tree and a pin that reads it has nothing to read there.
TRACKER_ABSENT_REASON = (
    ".phos_* is a forbidden path in public/manifest.toml, so the programme tracker is not in "
    "the public tree and this pin has nothing to read. In the lab, where the tracker is "
    "present, a moved digit still fails the pin."
)


#: Why the data-tier and docs-on-main rules are absent. `docs/rules/<name>.md` is a symlink into
#: `.cursor/rules/`, which `public/manifest.toml` forbids outright, so neither the link nor its
#: target reaches the public tree. A test that resolves a corpus tier has nothing to resolve it
#: against there (ADR 0416), and one that ran anyway would be exercising the unknown-corpus refusal
#: rather than the state it names.
RULES_ABSENT_REASON = (
    "docs/rules/ is a symlink into .cursor/rules/, a forbidden path in public/manifest.toml, so "
    "the data-tier rule is not in the public tree and a declaration has nothing to resolve a "
    "corpus tier against. In the lab, where the rule is present, a changed tier still fails."
)


#: Why the editor hook scripts are absent. `.cursor/*` and `.claude/*` are forbidden paths, so the
#: gate and guard shims never reach the public tree. **A test that reads them must skip rather than
#: pass**: several of these iterate a directory, and an absent directory yields no iterations, so
#: the assertion inside the loop never runs and the test goes green having checked nothing. That is
#: the "an empty register checks nothing" failure, in the test suite instead of on the page.
HOOKS_ABSENT_REASON = (
    ".cursor/ and .claude/ are forbidden paths in public/manifest.toml, so the editor hook "
    "scripts are not in the public tree. A test that iterated them there would find nothing and "
    "pass without checking anything. In the lab, where they are present, they are really driven."
)


def skip_if_absent(path: Path, reason: str = ABSENT_REASON) -> None:
    """Skip when ``path`` is not a file. A present file is checked by the caller.

    Args:
        path: The lab file the pin reads. Absence means the public export omitted it.
        reason: Why that file is absent, so the skip message names the right rule. Defaults to
            the `experiments/` case; pass `TRACKER_ABSENT_REASON` for a `.phos_*` tracker.
    """
    if path.is_file():
        return
    pytest.skip(f"{path} is absent. {reason}")
