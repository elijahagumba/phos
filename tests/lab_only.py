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
