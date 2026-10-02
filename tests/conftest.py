"""Skip ``lab_only`` tests in the public repository, where the records they read are absent."""

from pathlib import Path

import pytest

# The export manifest exists only in the lab, so its presence is what marks a lab checkout.
_LAB_MARKER = Path(__file__).resolve().parents[1] / "public" / "manifest.toml"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every ``lab_only`` test as skipped when this checkout is not the lab."""
    if _LAB_MARKER.is_file():
        return
    skip = pytest.mark.skip(reason="reads a lab-only record that is not published")
    for item in items:
        if item.get_closest_marker("lab_only") is not None:
            item.add_marker(skip)
