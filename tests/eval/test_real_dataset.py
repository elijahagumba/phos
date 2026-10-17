"""Integration tests against the real labelled ICS corpora.

Every corpus registered in ``data/registry.json`` and prepared by ``scripts/fetch_datasets.py``
is exercised here. The manifests are committed; the CSVs they describe are not, so each case
skips itself when its payload is absent and a fresh clone stays green without a download.

This is what proves the PART 2/3 code path works on real telemetry rather than only on the
synthetic generator — and it is deliberately parametrised over every corpus, because the traps
that break a real load (a label column whose sentinel means "unlabelled", column names that
differ between a corpus's own train and test files, ambiguous day-first dates) are per-corpus and
would not be caught by testing one of them. The module is marked ``slow`` (ADR 0092). With
the payloads on disk the two batch-distillation scores are about nine minutes each, and the
default suite omits the marker.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from phos.eval import (
    EvalConfig,
    EvaluationReport,
    LabelledCsvAdapter,
    ThresholdDetector,
    evaluate,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _resolve(config: dict[str, Any]) -> dict[str, Any] | None:
    """Return an adapter config with an absolute path, or ``None`` if its CSV is absent."""
    fields = {
        key: value
        for key, value in config.items()
        if key in LabelledCsvAdapter.model_fields and key != "path"
    }
    path = DATA_DIR / config["path"]
    return {**fields, "path": str(path)} if path.is_file() else None


def discover_manifests() -> list[tuple[str, dict[str, Any]]]:
    """Return every ``(case_id, adapter_config)`` whose corpus is present on disk.

    Two sources: the per-dataset manifests written by the fetch script, and the operator's own
    single-corpus ``data/manifest.json`` described in ``data/README.md``. A manifest's nested
    ``train`` block is picked up as its own case, so the attack-free training corpus is loaded
    and checked too.
    """
    cases: list[tuple[str, dict[str, Any]]] = []
    candidates: list[tuple[str, dict[str, Any]]] = []

    for manifest_path in sorted(DATA_DIR.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        name = manifest_path.parent.name
        candidates.append((name, manifest))
        if isinstance(manifest.get("train"), dict):
            candidates.append((f"{name}-train", manifest["train"]))

    operator = DATA_DIR / "manifest.json"
    if operator.is_file():
        candidates.append(("operator", json.loads(operator.read_text(encoding="utf-8"))))

    for case_id, manifest in candidates:
        resolved = _resolve(manifest)
        if resolved is not None:
            cases.append((case_id, resolved))
    return cases


MANIFESTS = discover_manifests()
CASES = [pytest.param(config, id=case_id) for case_id, config in MANIFESTS] or [
    pytest.param({}, id="none")
]

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not MANIFESTS,
        reason=(
            "no real corpus present; run scripts/fetch_datasets.py --all "
            f"(see {DATA_DIR}/README.md)"
        ),
    ),
    pytest.mark.parametrize("config", CASES),
]


def test_real_dataset_loads_into_the_ontology(config: dict[str, Any]) -> None:
    dataset = LabelledCsvAdapter.model_validate(config).load()

    assert dataset.observations, "corpus produced no observations"
    stamps = [observation.timestamp for observation in dataset.observations]
    assert stamps == sorted(stamps)
    assert all(stamp.tzinfo is not None for stamp in stamps)
    assert dataset.duration().total_seconds() > 0
    assert dataset.normal_duration() <= dataset.duration()


def test_real_dataset_labels_are_not_degenerate(config: dict[str, Any]) -> None:
    """Ground truth must mark some of the corpus normal.

    This is the regression test for the label trap that motivated the whole registry. BATADAL
    uses ``-999`` for "not labelled" across 95% of its test rows, and the shipped
    ``default_attack_when`` counts any non-zero value as an attack — so a naive load reports a
    corpus that is almost entirely under attack, and every metric computed from it is meaningless
    while looking perfectly plausible. A corpus with no normal time would divide by zero in the
    false-positive rate; one with no attacks cannot exercise recall.
    """
    dataset = LabelledCsvAdapter.model_validate(config).load()

    assert dataset.normal_duration().total_seconds() > 0, (
        f"{dataset.name} has no normal time at all — the label column is almost certainly "
        "being misread; check attack_when against the corpus's real label values"
    )
    normal_fraction = dataset.normal_duration().total_seconds() / dataset.duration().total_seconds()
    # S1 is a ~30-minute labelled experiment: 913/1798 rows are attack_active (~51%).
    # That is the files (ADR 0046), not the BATADAL -999 trap (~100% attack). Pin a band
    # so a misread that flipped S1 to "almost all attack" still fails.
    attack_dense = {"data4cyber-test": (0.45, 0.55)}
    bounds = attack_dense.get(dataset.name)
    if bounds is not None:
        low, high = bounds
        assert low < normal_fraction < high, (
            f"{dataset.name} normal fraction {normal_fraction:.3f} is outside the S1 band "
            f"[{low}, {high}]; check attack_active mapping"
        )
        return
    assert normal_fraction > 0.5, (
        f"{dataset.name} is {1 - normal_fraction:.0%} attack by duration, which no published "
        "ICS corpus is; the label semantics are wrong"
    )


def test_real_dataset_scores_end_to_end(config: dict[str, Any]) -> None:
    dataset = LabelledCsvAdapter.model_validate(config).load()
    report = evaluate(ThresholdDetector(), dataset, EvalConfig(alert_threshold=3.0))

    assert report.dataset_name == dataset.name
    assert report.n_observations == len(dataset.observations)
    assert 0.0 <= report.window_recall <= 1.0
    assert 0.0 <= report.precision <= 1.0
    assert 0.0 <= report.recall_sample <= 1.0
    assert 0.0 <= report.f1 <= 1.0
    assert report.false_positive_rate >= 0.0
    assert 0.0 <= report.expected_calibration_error <= 1.0
    assert 0.0 <= report.brier_score <= 1.0
    assert report.latency.count <= report.n_attack_intervals
    # Every alert is a true positive, a false positive, or set aside in unscored time (ADR 0082).
    assert (
        sum(row.count for row in report.reliability) == report.n_alerts - report.n_unscored_alerts
    )


def test_real_dataset_report_round_trips(config: dict[str, Any]) -> None:
    dataset = LabelledCsvAdapter.model_validate(config).load()
    report = evaluate(ThresholdDetector(), dataset, EvalConfig(alert_threshold=3.0))
    assert EvaluationReport.model_validate_json(report.model_dump_json()) == report
