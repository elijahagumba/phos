"""Tests for entity-scoped ground truth read from CERT's answers archive."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from phos.eval import LabelledInterval
from phos.sentiel import EntityLabelledInterval, malicious_user_ids, read_insiders

MALLORY_START = datetime(2010, 1, 4, 22, 30, tzinfo=UTC)
MALLORY_END = datetime(2010, 1, 4, 23, 59, 59, tzinfo=UTC)


def test_reads_the_release_it_was_asked_for(answers_dir: Path) -> None:
    labels = read_insiders(answers_dir, "r3.1")

    assert len(labels) == 1
    assert labels[0].user_id == "MALLORY9"
    assert labels[0].start == MALLORY_START
    assert labels[0].end == MALLORY_END
    assert labels[0].scenario == "1"
    assert labels[0].release == "3.1"


def test_the_leading_r_is_optional(answers_dir: Path) -> None:
    assert read_insiders(answers_dir, "3.1") == read_insiders(answers_dir, "r3.1")


def test_reading_every_release_keeps_them_all(answers_dir: Path) -> None:
    assert {label.user_id for label in read_insiders(answers_dir)} == {"MALLORY9", "SOMEONE1"}


def test_an_unpadded_month_parses(answers_dir: Path) -> None:
    """insiders.csv mixes `3/6/2010` and `07/01/2010`; one format must read both."""
    someone = next(label for label in read_insiders(answers_dir) if label.user_id == "SOMEONE1")
    assert someone.start == datetime(2010, 3, 6, 1, 41, 56, tzinfo=UTC)


def test_the_file_or_its_directory_may_be_given(answers_dir: Path) -> None:
    assert read_insiders(answers_dir / "insiders.csv", "3.1") == read_insiders(answers_dir, "3.1")


def test_labels_are_sorted_by_start(answers_dir: Path) -> None:
    labels = read_insiders(answers_dir)
    assert [label.start for label in labels] == sorted(label.start for label in labels)


def test_a_release_with_no_rows_is_refused(answers_dir: Path) -> None:
    """An empty label set scores every detector at zero recall while looking like a real run."""
    with pytest.raises(ValueError, match="no ground-truth rows"):
        read_insiders(answers_dir, "r9.9")


def test_a_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_insiders(tmp_path / "answers")


def test_a_missing_column_raises(tmp_path: Path) -> None:
    path = tmp_path / "insiders.csv"
    path.write_text("dataset,scenario,user\n3.1,1,X\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required column"):
        read_insiders(path)


def test_an_unparseable_timestamp_raises(tmp_path: Path) -> None:
    path = tmp_path / "insiders.csv"
    path.write_text(
        "dataset,scenario,details,user,start,end\n3.1,1,x.csv,X,2010-01-04,01/04/2010 23:00:00\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="matches none of"):
        read_insiders(path)


def test_an_inverted_window_is_rejected() -> None:
    with pytest.raises(ValueError, match="inverted"):
        EntityLabelledInterval(user_id="X", start=MALLORY_END, end=MALLORY_START)


class TestContains:
    """`contains` is the whole thesis of the module: both halves must match."""

    label = EntityLabelledInterval(user_id="MALLORY9", start=MALLORY_START, end=MALLORY_END)

    def test_the_right_user_inside_the_window_is_covered(self) -> None:
        assert self.label.contains("MALLORY9", datetime(2010, 1, 4, 23, 0, tzinfo=UTC))

    def test_the_wrong_user_inside_the_window_is_not_covered(self) -> None:
        assert not self.label.contains("ALICE001", datetime(2010, 1, 4, 23, 0, tzinfo=UTC))

    def test_the_right_user_outside_the_window_is_not_covered(self) -> None:
        assert not self.label.contains("MALLORY9", datetime(2010, 1, 5, 12, 0, tzinfo=UTC))

    def test_both_bounds_are_inclusive(self) -> None:
        assert self.label.contains("MALLORY9", MALLORY_START)
        assert self.label.contains("MALLORY9", MALLORY_END)


def test_projection_to_a_part_2_interval_keeps_the_window_and_the_scenario() -> None:
    label = EntityLabelledInterval(
        user_id="MALLORY9", start=MALLORY_START, end=MALLORY_END, scenario="1"
    )
    projected = label.as_labelled_interval()

    assert isinstance(projected, LabelledInterval)
    assert (projected.start, projected.end) == (MALLORY_START, MALLORY_END)
    assert projected.attack_type == "scenario-1"


def test_projection_drops_the_user_which_is_why_it_is_documented_as_unsafe_alone() -> None:
    """PART 2's type cannot carry a user — that is the seam, and it is one-way."""
    projected = EntityLabelledInterval(
        user_id="MALLORY9", start=MALLORY_START, end=MALLORY_END
    ).as_labelled_interval()
    assert "user_id" not in type(projected).model_fields


def test_malicious_user_ids_collects_the_distinct_users(answers_dir: Path) -> None:
    assert malicious_user_ids(read_insiders(answers_dir)) == {"MALLORY9", "SOMEONE1"}
