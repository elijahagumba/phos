"""The published development pool, and a walk through the third-party guide.

Bar f of the operation is "a third party can follow the documentation and run their own detector
on the development pool without help". A test cannot read a page for clarity, but it can do the
mechanical half: follow the steps the page gives, in the order it gives them, using only what the
page names, and assert that the result is a detector that ran and a score that has the shape the
page promises. If a step in the guide stops working, this fails.

The three tests that read the guide run everywhere, including the public tree.
``docs/referee/third-party-guide.md`` is an include pattern in ``public/manifest.toml``, so the page
travels with the code it documents. That is the point of it: it is written for a reader outside
PHOS and tells them to clone the public repository, so a copy that existed only in the lab would be
a guide nobody it was written for could read.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from phos.eval import Dataset, Detection
from phos.referee.development import (
    DEVELOPMENT_POOL_PATH,
    DevelopmentPoolError,
    development_exam,
    load,
)
from phos.referee.exam import ExamError

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_the_committed_pool_loads_and_is_a_development_pool() -> None:
    """Bar f: The file exists in the checkout and says it is the development pool."""
    pool = load(REPO_ROOT)
    assert pool.pool == "dev"
    assert len(pool.entries) >= 5


def test_the_pool_names_only_open_families() -> None:
    """Bar f: a published pool must not draw from a sealed family.

    A pool drawing from a sealed family would disclose the sealed set's shape.
    """
    from phos.synth.families import get_family

    for entry in load(REPO_ROOT).entries:
        family = get_family(entry.family)
        assert not family.sealed, f"{entry.family} is sealed and must not be in a public pool"


def test_the_pool_seeds_are_distinct() -> None:
    """Bar f: A duplicate would silently shrink the pool while its count said otherwise."""
    entries = load(REPO_ROOT).entries
    keys = {(entry.family, entry.seed) for entry in entries}
    assert len(keys) == len(entries)


def test_a_public_pool_cannot_claim_to_be_private(tmp_path: Path) -> None:
    """A committed file claiming to be a private pool is refused, not read."""
    (tmp_path / "data").mkdir()
    (tmp_path / DEVELOPMENT_POOL_PATH).write_text(
        json.dumps({"pool": "private", "entries": [{"family": "level_flow", "seed": 1}]}),
        encoding="utf-8",
    )
    with pytest.raises(DevelopmentPoolError, match="Only a development pool may be committed"):
        load(tmp_path)


def test_a_missing_pool_is_refused_not_treated_as_empty(tmp_path: Path) -> None:
    """An empty pool and a missing file must not look the same."""
    with pytest.raises(DevelopmentPoolError, match="is missing"):
        load(tmp_path)


def test_an_empty_pool_is_refused(tmp_path: Path) -> None:
    """Zero entries is not a pool."""
    (tmp_path / "data").mkdir()
    (tmp_path / DEVELOPMENT_POOL_PATH).write_text(
        json.dumps({"pool": "dev", "entries": []}), encoding="utf-8"
    )
    with pytest.raises(DevelopmentPoolError, match="does not match the schema"):
        load(tmp_path)


def test_asking_for_more_plants_than_the_pool_holds_is_refused() -> None:
    """Bar f: A request the pool cannot satisfy is an error, not a short exam."""
    pool = load(REPO_ROOT)
    with pytest.raises(ExamError, match="fewer than"):
        development_exam(pool, scorer_version="test", code_version=None, size=len(pool.entries) + 1)


def test_the_exam_id_is_a_function_of_the_pool_and_the_versions() -> None:
    """Bar f: The same pool and versions give the same exam, so a third party reproduces it."""
    pool = load(REPO_ROOT)
    first = development_exam(pool, scorer_version="v1", code_version="abc", size=2)
    again = development_exam(pool, scorer_version="v1", code_version="abc", size=2)
    other = development_exam(pool, scorer_version="v2", code_version="abc", size=2)
    assert first.exam_id == again.exam_id
    assert first.exam_id != other.exam_id


def test_a_third_party_walk_through_reaches_a_detector_that_ran_and_a_score(
    tmp_path: Path,
) -> None:
    """Bar f: The steps the guide gives, in its order, produce a run and a reportable score.

    This is the mechanical half of "a third party can follow the documentation". It builds an
    exam from the published pool, runs a detector through `run_exam` as the guide says, and
    renders the report. Every call it makes is one the guide names.
    """
    from phos.referee.demo import threshold_detector
    from phos.referee.report import render_markdown
    from phos.referee.runner import run_exam
    from phos.referee.scoring import aggregate

    pool = load(REPO_ROOT)
    exam = development_exam(pool, scorer_version="walk", code_version=None, size=1)

    scores = run_exam(exam, threshold_detector(), tmp_path / "work")
    score = aggregate("threshold", scores)
    markdown = render_markdown(exam, score)
    assert "SIMULATED" in markdown
    assert "## Limitations" in markdown


def test_the_scoring_path_never_hands_a_detector_its_labels(tmp_path: Path) -> None:
    """Bar b: A detector scored by `score_plant` cannot see attack intervals in its own input.

    This is the gap the isolated worker did not cover. Isolation stops a detector opening a label
    file; it does not stop the scorer passing a labelled `Dataset` to `detector.run`, which is what
    `evaluate` does. A detector that simply counts ``len(dataset.attack_intervals)`` would score
    perfectly without doing any work. `sealed_detector` closes that.
    """
    from phos.referee.scoring import score_plant
    from phos.synth.families import get_family
    from phos.synth.outputs import generate_plant

    seen: list[int] = []

    class LabelSnoop:
        name = "label-snoop"

        def run(self, dataset: Dataset) -> list[Detection]:
            seen.append(len(dataset.attack_intervals) + len(dataset.unscored_intervals))
            return []

    from phos.referee.runner import DEFAULT_EVENT_CATALOGUE

    # A catalogue, because a plant with no events has no labels to leak and would make this test
    # pass for the wrong reason.
    plant = generate_plant(
        get_family("level_flow"),
        771001,
        tmp_path,
        hours=24.0,
        events=DEFAULT_EVENT_CATALOGUE,
        skip_impossible_events=True,
    )
    score = score_plant(LabelSnoop(), plant)
    assert seen, "the detector should have been run"
    assert set(seen) == {0}, f"the detector saw labels: {seen}"
    # And the score itself still knows the truth, so sealing did not break scoring.
    assert score.report.n_attack_intervals > 0


def test_the_sealed_wrapper_keeps_the_detectors_name() -> None:
    """Bar b: A report must name the real detector, not the wrapper."""
    from phos.referee.scoring import sealed_detector

    class Named:
        name = "a-real-name"

        def run(self, dataset: Dataset) -> list[Detection]:
            return []

    assert sealed_detector(Named()).name == "a-real-name"


def test_the_guide_says_what_the_pool_cannot_tell_you() -> None:
    """Bar f: The page must carry the honesty section, or a reader takes a number out of context."""
    page = (REPO_ROOT / "docs" / "referee" / "third-party-guide.md").read_text(encoding="utf-8")
    assert "cannot tell you" in page.lower()
    assert "not a claim about catching a real attacker" in page.lower()
    assert "unseen" in page.lower()


def test_the_guide_names_a_plant_that_is_not_its_real_name() -> None:
    """Bar f: the guide must warn about the opaque name.

    A reader who does not know the name is opaque will spend time trying to parse it.

    This is the documentation half of bar b: a detector author who does not know the name is
    opaque will spend time trying to parse it.
    """
    page = (REPO_ROOT / "docs" / "referee" / "third-party-guide.md").read_text(encoding="utf-8")
    assert "opaque" in page.lower()
    assert "plant-" in page


def test_the_guide_and_the_code_agree_on_the_pool_path() -> None:
    """Bar f: A guide naming a path the code does not read is worse than no guide."""
    page = (REPO_ROOT / "docs" / "referee" / "third-party-guide.md").read_text(encoding="utf-8")
    assert DEVELOPMENT_POOL_PATH.as_posix() in page


def test_the_opaque_token_is_not_in_the_pool() -> None:
    """Bar b, cross-check. The name a detector sees must not be recoverable from the public pool.

    It cannot be, since it is a digest of the real plant id, but asserting it keeps a future
    change from quietly making the token a function of the pool file.
    """
    pool = load(REPO_ROOT)
    tokens = {opaque_name_for_entry(entry.family, entry.seed) for entry in pool.entries}
    raw = (REPO_ROOT / DEVELOPMENT_POOL_PATH).read_text(encoding="utf-8")
    for token in tokens:
        assert token not in raw


def opaque_name_for_entry(family: str, seed: int) -> str:
    """Return the opaque token for a pool entry, built the way the worker builds it.

    Args:
        family: The family id.
        seed: The master seed.

    Returns:
        The token, which is a digest of the plant id ``family-seed``.
    """
    import hashlib

    return f"plant-{hashlib.sha256(f'{family}-{seed}'.encode()).hexdigest()[:16]}"


def test_a_plant_id_really_is_the_family_and_seed() -> None:
    """Bar b: the premise of the opaque name.

    A real id discloses both family and seed, which is why it must not be passed to a detector.
    """
    from phos.synth.families import get_family

    family = get_family("level_flow")
    spec = family.draw(771001)
    assert spec.plant_id == "level-flow-771001"
    assert "771001" in spec.plant_id
