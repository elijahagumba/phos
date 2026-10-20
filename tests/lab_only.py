"""Skip a lab pin when the public export did not carry the file."""

from __future__ import annotations

from pathlib import Path

import pytest

ABSENT_REASON = (
    "experiments/ is not an include pattern in public/manifest.toml, so this pin is not in "
    "the public tree. Exporting the small text file is the alternative. In a checkout where "
    "the file is present, a moved byte still fails the pin."
)


def skip_if_absent(path: Path) -> None:
    """Skip when ``path`` is not a file. A present file is checked by the caller.

    Args:
        path: The lab file the pin reads. Absence means the public export omitted it.
    """
    if path.is_file():
        return
    pytest.skip(f"{path} is absent. {ABSENT_REASON}")
