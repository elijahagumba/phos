"""The clean HAI run is declared here and is not executed by these tests."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from phos.eval.baseline_table import DETECTORS, CorpusReport, DetectorScore, FileScore
from phos.eval.clean_hai import (
    CLEAN_CORPORA,
    CLEAN_JSON_NAME,
    DECLARED_FEATURES,
    HAI_2204_ATTACKS,
    HAI_2204_TEST_ATTACKS,
    HAI_2204_TRAIN_ATTACKS,
    HAI_2305_ATTACKS,
    HAI_2305_SUMMARY_HEADER_ATTACKS,
    HAI_2305_TEST_ATTACKS,
    PUBLISHED_GUARD,
    assert_declared_counts,
    attack_runs,
    features_hai_2204,
    features_hai_2305,
    label_columns_hai_2305,
    splice_clean_json,
    splice_clean_markdown,
)
from phos.eval.grouped_rows import GROUPED_ATLAS, GROUPED_CORPORA, GroupedRow, exposure_of

ROOT = Path(__file__).resolve().parents[2]
TABLE = ROOT / "eval_runs" / "v1" / "g1-baseline-table.md"


def test_the_clean_corpora_are_the_two_later_editions() -> None:
    """22.04 and 23.05, in that order, and nowhere else in this declaration."""
    assert CLEAN_CORPORA == ("hai-22.04", "hai-23.05")
    assert set(CLEAN_CORPORA).isdisjoint(GROUPED_CORPORA)
    assert all(exposure_of(corpus) is None for corpus in CLEAN_CORPORA)
    assert sum(HAI_2204_TEST_ATTACKS.values()) == HAI_2204_ATTACKS == 58
    assert sum(HAI_2305_TEST_ATTACKS.values()) == HAI_2305_ATTACKS == 52
    assert HAI_2305_SUMMARY_HEADER_ATTACKS == 40
    assert HAI_2305_SUMMARY_HEADER_ATTACKS != HAI_2305_TEST_ATTACKS["hai-test2.csv"]
    assert set(HAI_2204_TRAIN_ATTACKS.values()) == {0}
    assert CLEAN_JSON_NAME == "g1-clean-hai.json"


def test_attack_runs_count_contiguous_true_cells() -> None:
    """A run is a stretch of attacks, not a count of attack rows."""
    assert attack_runs((False, True, True, False, True)) == 2
    assert attack_runs(()) == 0


def test_headers_match_the_declared_contracts() -> None:
    """22.04 ends in Attack. 23.05 series has no label. Label files are two columns."""
    tags = [f"tag{index}" for index in range(DECLARED_FEATURES)]
    assert features_hai_2204(("timestamp", *tags, "Attack")) == tuple(tags)
    assert features_hai_2305(("timestamp", *tags)) == tuple(tags)
    label_columns_hai_2305(("timestamp", "label"))
    with pytest.raises(ValueError, match="one Attack column"):
        features_hai_2204(("timestamp", "attack_P1", *tags[1:], "Attack"))
    with pytest.raises(ValueError, match="no Attack column"):
        features_hai_2305(("timestamp", *tags, "Attack"))
    with pytest.raises(ValueError, match="timestamp,label"):
        label_columns_hai_2305(("timestamp", "Attack"))


def test_a_count_that_is_not_the_declaration_is_refused() -> None:
    """The run stops before a fit when a file's runs are not the written-down count."""
    assert_declared_counts("hai-22.04", HAI_2204_TEST_ATTACKS)
    with pytest.raises(ValueError, match="attack runs"):
        assert_declared_counts("hai-23.05", {"hai-test1.csv": 14, "hai-test2.csv": 40})


def test_the_splice_fills_the_placeholders_and_keeps_the_published_row() -> None:
    """A fake score edits only the two unscored slots. The 9/38 line stays."""
    text = _unscored_markdown()
    reports = (_report("hai-22.04", 1, 58), _report("hai-23.05", 2, 52))
    grouped = (_grouped("hai-22.04", -3), _grouped("hai-23.05", 1))
    updated = splice_clean_markdown(text, reports, grouped)
    assert updated.count(PUBLISHED_GUARD) == 1
    assert "not on disk" not in updated
    assert "| hai-22.04 | yes | — | — | — | — | not scored |" not in updated
    assert (
        "| hai-22.04 | yes | g1-baseline:atlas-mahalanobis | engine | 1 | 58 | 0.017241 |"
        in updated
    )
    assert "hai-23.05: beyond grouping 1" in updated
    assert "are not labelled seen" in updated
    assert "not scored" in text


def test_the_json_splice_leaves_a_frozen_float_byte_for_byte() -> None:
    """Replacing the two objects does not reformat a frozen float sitting beside them."""
    from phos.eval.clean_hai import _JSON_NOT_SCORED

    frozen = "0.23684210526315788"
    original = frozen + "\n" + _JSON_NOT_SCORED["hai-22.04"] + ",\n" + _JSON_NOT_SCORED["hai-23.05"]
    reports = (_report("hai-22.04", 1, 58), _report("hai-23.05", 2, 52))
    updated = splice_clean_json(original, reports)
    assert updated.count(frozen) == 1
    assert "not on disk" not in updated
    assert '"corpus": "hai-22.04"' in updated


def test_the_clean_run_is_in_the_table() -> None:
    """The one run filled the placeholders and left the published 9/38 row."""
    text = TABLE.read_text(encoding="utf-8")
    assert text.count(PUBLISHED_GUARD) == 1
    assert "not on disk" not in text
    assert "| hai-22.04 | yes | g1-baseline:atlas-mahalanobis | engine | 5 | 58 |" in text
    assert "| hai-23.05 | yes | g1-baseline:atlas-mahalanobis | engine | 3 | 52 |" in text
    assert "hai-22.04: beyond grouping -5" in text
    assert "hai-23.05: beyond grouping -1" in text
    assert (ROOT / "eval_runs" / "v1" / CLEAN_JSON_NAME).is_file()
    script = (ROOT / "scripts" / "measure_clean_hai.py").read_text(encoding="utf-8")
    assert "append_to_experiment_log" not in script


def _unscored_markdown() -> str:
    from phos.eval.clean_hai import _GROUPED_SENTENCE, _NOT_ON_DISK, _NOT_SCORED_ROW, _NOTE_LINE

    return "\n".join(
        [
            PUBLISHED_GUARD,
            _NOT_SCORED_ROW["hai-22.04"],
            _NOT_SCORED_ROW["hai-23.05"],
            (
                "| hai-21.03 | g1-baseline:simple-histogram | 0.240000 | "
                "0.251549 | 0.328474 | 0.432224 | 1709 |"
            ),
            _NOT_ON_DISK["hai-22.04"],
            _NOT_ON_DISK["hai-23.05"],
            _NOTE_LINE["hai-22.04"],
            _NOTE_LINE["hai-23.05"],
            _GROUPED_SENTENCE,
            "## Grouped notes",
            "",
        ]
    )


@pytest.mark.slow
def test_on_disk_attack_runs_match_the_declaration() -> None:
    """Recount the label columns. This does not fit a detector."""
    root = ROOT / "data"
    edition = root / "hai-22.04" / "test1.csv"
    if not edition.is_file():
        pytest.skip("HAI 22.04 payloads are not on disk")
    counted = {name: _runs(root / "hai-22.04" / name, "Attack") for name in HAI_2204_TEST_ATTACKS}
    assert counted == dict(HAI_2204_TEST_ATTACKS)
    trains = {name: _runs(root / "hai-22.04" / name, "Attack") for name in HAI_2204_TRAIN_ATTACKS}
    assert trains == dict(HAI_2204_TRAIN_ATTACKS)
    labels = root / "hai-23.05" / "label-test1.csv"
    if not labels.is_file():
        pytest.skip("HAI 23.05 payloads are not on disk")
    later = {
        "hai-test1.csv": _runs(root / "hai-23.05" / "label-test1.csv", "label"),
        "hai-test2.csv": _runs(root / "hai-23.05" / "label-test2.csv", "label"),
    }
    assert later == dict(HAI_2305_TEST_ATTACKS)
    header = _header(root / "hai-23.05" / "hai-test2.csv")
    label_header = _header(root / "hai-23.05" / "label-test2.csv")
    assert header[0] == "timestamp" and "Attack" not in header
    assert tuple(label_header) == ("timestamp", "label")
    assert len(features_hai_2305(header)) == DECLARED_FEATURES


def _runs(path: Path, column: str) -> int:
    flags: list[bool] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or column not in reader.fieldnames:
            raise AssertionError(f"{path.name} has no {column}")
        for row in reader:
            flags.append(row[column] not in {"0", "0.0", ""})
    return attack_runs(flags)


def _header(path: Path) -> list[str]:
    with path.open(encoding="utf-8") as handle:
        return handle.readline().rstrip("\n").split(",")


def _report(corpus: str, caught: int, attacks: int) -> CorpusReport:
    scores = tuple(
        DetectorScore(
            detector=name,
            attacks=attacks,
            caught=caught if name.endswith("atlas-mahalanobis") else 0,
            recall_within_budget=(caught / attacks) if name.endswith("atlas-mahalanobis") else 0.0,
            etapr_reference_f1=0.0,
            etapr_haicon_f1=0.0,
            point_adjusted_f1=0.0,
            alerts=1,
        )
        for name in DETECTORS
    )
    return CorpusReport(
        corpus=corpus,
        judges=True,
        status="scored",
        note="declared test row",
        sample_period_seconds=1.0,
        declared_period_seconds=1.0,
        files=(FileScore("test.csv", scores),),
    )


def _grouped(corpus: str, gap: int) -> GroupedRow:
    score = DetectorScore(
        detector=GROUPED_ATLAS,
        attacks=10,
        caught=1,
        recall_within_budget=0.1,
        etapr_reference_f1=0.0,
        etapr_haicon_f1=0.0,
        point_adjusted_f1=0.0,
        alerts=1,
    )
    opponents = tuple(
        DetectorScore(
            detector=f"g1-grouped:simple-{name}",
            attacks=10,
            caught=0,
            recall_within_budget=0.0,
            etapr_reference_f1=0.0,
            etapr_haicon_f1=0.0,
            point_adjusted_f1=0.0,
            alerts=0,
        )
        for name in ("minmax", "steadytime", "histogram")
    )
    return GroupedRow(
        corpus=corpus,
        exposure=None,
        scores=(score, *opponents),
        beyond_grouping=gap,
        attacks_only_grouped_atlas=(),
        note="declared grouped row",
    )
