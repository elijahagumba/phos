"""Grade B (ADR 0130, ADR 0132): links seen to propagate from logged changes."""

import ast
from pathlib import Path

import numpy

from phos.atlas.interventions import Intervention, intervened_links

NAMES = ("setpoint", "level", "noise", "drifting")
ROWS = 6_000
CHANGES = (1_000, 2_000, 3_000, 4_000, 5_000)


def _file(seed: int) -> numpy.ndarray:
    rng = numpy.random.default_rng(seed)
    out = numpy.zeros((ROWS, len(NAMES)))
    setpoint = 5.0
    level = 5.0
    for t in range(ROWS):
        if t in CHANGES:
            setpoint += 1.0 if (CHANGES.index(t) % 2 == 0) else -1.0
        level += 0.05 * (setpoint - level)  # follows the setpoint within a minute
        out[t] = (
            setpoint,
            level + rng.normal(0, 0.02),
            rng.normal(0, 1.0),
            # moves a little before every change, as a coincident disturbance would
            float(any(c - 150 <= t < c for c in CHANGES)) * 3.0 + rng.normal(0, 0.05),
        )
    return out


def _changes(files: int) -> list[Intervention]:
    return [Intervention(f, row, "setpoint") for f in range(files) for row in CHANGES]


def test_a_signal_that_responds_to_every_change_is_an_intervened_link() -> None:
    links = intervened_links([_file(1), _file(2)], NAMES, _changes(2), 1.0)
    found = {(link.driver, link.driven): link for link in links}
    assert ("setpoint", "level") in found
    assert found[("setpoint", "level")].responses == found[("setpoint", "level")].changes == 10


def test_noise_and_a_signal_that_moves_first_are_not_links() -> None:
    links = intervened_links([_file(1), _file(2)], NAMES, _changes(2), 1.0)
    driven = {link.driven for link in links}
    assert "noise" not in driven
    assert "drifting" not in driven


def test_too_few_changes_make_no_link() -> None:
    changes = [Intervention(0, row, "setpoint") for row in CHANGES[:2]]
    assert intervened_links([_file(1)], NAMES, changes, 1.0) == ()


def test_nothing_under_atlas_reads_the_icssim_truth() -> None:
    atlas = Path(__file__).resolve().parents[2] / "src" / "phos" / "atlas"
    for path in atlas.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                assert node.module != "phos.breaking.icssim_truth", path
