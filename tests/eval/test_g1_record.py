"""The G1 rebuild checks development rows and reprints validation rows."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from phos.eval.baseline_report import render_report
from phos.eval.baseline_table import DETECTORS, CorpusReport, DetectorScore, FileScore
from phos.eval.g1_record import (
    DEVELOPMENT_CORPORA,
    GROUPED_HEADING,
    TABLE_ORDER,
    VALIDATION_CORPORA,
    RecordMismatchError,
    rebuild_markdown,
)


def test_a_matching_recompute_reprints_the_validation_digits() -> None:
    fresh, recorded, markdown = _fixture()
    rebuilt = rebuild_markdown(markdown, recorded, fresh)
    assert rebuilt == markdown
    assert "| hai-21.03 | yes | g1-baseline:atlas-mahalanobis | engine | 7 | 50 |" in rebuilt
    assert "| batadal | yes | g1-baseline:atlas-mahalanobis | engine | 5 | 5 |" in rebuilt
    assert "validation-grouped-line" in rebuilt


def test_a_development_mismatch_does_not_return_a_table() -> None:
    fresh, recorded, markdown = _fixture()
    changed = dict(fresh)
    changed["hai-20.07"] = _report("hai-20.07", True, "scored", caught=8, attacks=38)
    with pytest.raises(RecordMismatchError, match=r"hai-20\.07 corpus detector 0 caught"):
        rebuild_markdown(markdown, recorded, changed)


def test_an_unscored_validation_row_is_not_reprinted_as_a_score() -> None:
    fresh, recorded, markdown = _fixture()
    recorded[1] = {**recorded[1], "status": "not_scored", "scores": []}
    with pytest.raises(RecordMismatchError, match=r"hai-21\.03 is not a scored row"):
        rebuild_markdown(markdown, recorded, fresh)


def test_the_three_development_corpora_are_the_only_ones_recomputed() -> None:
    assert DEVELOPMENT_CORPORA == ("hai-20.07", "batch-distillation", "data4cyber")
    assert VALIDATION_CORPORA == ("hai-21.03", "hai-22.04", "hai-23.05", "batadal")
    assert TABLE_ORDER[0] == "hai-20.07"


def _fixture() -> tuple[
    dict[str, CorpusReport],
    list[Mapping[str, object]],
    str,
]:
    reports = {
        "hai-20.07": _report("hai-20.07", True, "scored", caught=9, attacks=38),
        "hai-21.03": _report("hai-21.03", True, "scored", caught=7, attacks=50),
        "hai-22.04": _report("hai-22.04", True, "scored", caught=5, attacks=58),
        "hai-23.05": _report("hai-23.05", True, "scored", caught=3, attacks=52),
        "batadal": _report("batadal", True, "scored", caught=5, attacks=5),
        "batch-distillation": _report(
            "batch-distillation", False, "reported", caught=21, attacks=126
        ),
        "data4cyber": _report("data4cyber", False, "reported", caught=0, attacks=2),
    }
    recorded: list[Mapping[str, object]] = [_corpus(reports[name]) for name in TABLE_ORDER]
    rendered = render_report(tuple(reports[name] for name in TABLE_ORDER))
    markdown = rendered + "\n" + f"{GROUPED_HEADING}\n\nvalidation-grouped-line\n"
    fresh = {name: reports[name] for name in DEVELOPMENT_CORPORA}
    return fresh, recorded, markdown


def _corpus(report: CorpusReport) -> dict[str, object]:
    return {
        "corpus": report.corpus,
        "judges": report.judges,
        "status": report.status,
        "note": report.note,
        "sample_period_seconds": report.sample_period_seconds,
        "declared_period_seconds": report.declared_period_seconds,
        "scores": [_score(score) for score in report.scores],
        "files": [
            {"file": file.file, "scores": [_score(score) for score in file.scores]}
            for file in report.files
        ],
    }


def _score(score: DetectorScore) -> dict[str, object]:
    return {
        "detector": score.detector,
        "attacks": score.attacks,
        "caught": score.caught,
        "recall_within_budget": score.recall_within_budget,
        "etapr_reference_f1": score.etapr_reference_f1,
        "etapr_haicon_f1": score.etapr_haicon_f1,
        "point_adjusted_f1": score.point_adjusted_f1,
        "alerts": score.alerts,
    }


def _report(corpus: str, judges: bool, status: str, *, caught: int, attacks: int) -> CorpusReport:
    scores = tuple(
        DetectorScore(
            detector=name,
            attacks=attacks,
            caught=caught,
            recall_within_budget=caught / attacks,
            etapr_reference_f1=0.1,
            etapr_haicon_f1=0.2,
            point_adjusted_f1=0.3,
            alerts=4,
        )
        for name in DETECTORS
    )
    return CorpusReport(
        corpus=corpus,
        judges=judges,
        status=status,
        note="hand",
        sample_period_seconds=1.0,
        declared_period_seconds=1.0,
        files=(FileScore("test.csv", scores),),
    )
