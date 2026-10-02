"""Freeze the published Sentiel negatives. This file is the work.

Sentiel stays idle for detector retune. These tests do not remeasure CERT, do not change
``AggregationPolicy`` defaults, do not invent a contradictory template, and do not revive
peer-group advantage. They pin what the tracker, ADR 0032, and ADR 0023 already published, and
they pin the competing-set IDs the code actually registers.

JSON and ADR win over README. Code wins over README on template names. 6B remains the public
row; ``:precision`` remains a measured loss. Hypothesis confidence remains uncalibrated. This
is not a live-SOC claim.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

import pytest

from phos.reasoning import INSUFFICIENT_EVIDENCE_TEMPLATE_ID
from phos.sentiel import (
    BENIGN_ROLE_CHANGE_TEMPLATE_ID,
    COMPROMISED_ACCOUNT_TEMPLATE_ID,
    INSIDER_MISUSE_TEMPLATE_ID,
    PEER_ANOMALY_TEMPLATE_ID,
    SENTIEL_VERTICAL_CAVEATS,
    UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT,
    AggregationPolicy,
    precision_policy,
    sentiel_templates,
)

REPO: Final = Path(__file__).resolve().parents[2]
ROADMAP: Final = REPO / ".phos_roadmap_state.json"
SENTIEL_SRC: Final = REPO / "src" / "phos" / "sentiel"
ENGINE_SRC: Final = SENTIEL_SRC / "engine.py"

# ADR 0032 / frozen_measurements.cert_r31_at_48_alerts. Do not "fix" 6B.
_PUBLIC_6B_PRECISION: Final = 0.104
_PUBLIC_6B_TRUE_POSITIVES: Final = 5
_PUBLIC_6B_FALSE_POSITIVES: Final = 43
_PUBLIC_6B_WINDOW_RECALL: Final = 0.5
_PRECISION_POLICY_AT_48: Final = 0.083
_PUBLIC_HEADLINE: Final = "aggregate:gaussian:peer set (34 features) (6B)"

# Code wins over README: the sanctioned-change template is benign_role_change, not
# legitimate_change.
_COMPETING_SET_IDS: Final = frozenset(
    {
        "compromised_account",
        "insider_misuse",
        "peer_anomaly",
        "benign_role_change",
        "insufficient_evidence",
    }
)


def _as_mapping(value: object, path: str) -> dict[str, object]:
    """Return ``value`` as a JSON object, or fail with ``path`` in the message."""
    if not isinstance(value, dict):
        raise AssertionError(f"{path} must be a JSON object, got {type(value).__name__}")
    return {str(key): item for key, item in value.items()}


def _as_str(value: object, path: str) -> str:
    """Return ``value`` as a string."""
    if not isinstance(value, str):
        raise AssertionError(f"{path} must be a string, got {type(value).__name__}")
    return value


def _as_bool(value: object, path: str) -> bool:
    """Return ``value`` as a bool (rejects ``int``)."""
    if not isinstance(value, bool):
        raise AssertionError(f"{path} must be a bool, got {type(value).__name__}")
    return value


def _as_int(value: object, path: str) -> int:
    """Return ``value`` as an int (rejects ``bool``)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise AssertionError(f"{path} must be an int, got {type(value).__name__}")
    return value


def _as_float(value: object, path: str) -> float:
    """Return ``value`` as a number (rejects ``bool``)."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise AssertionError(f"{path} must be a number, got {type(value).__name__}")
    return float(value)


def _frozen_measurements() -> dict[str, object]:
    """Load ``frozen_measurements`` from the live programme tracker."""
    payload = _as_mapping(json.loads(ROADMAP.read_text(encoding="utf-8")), ROADMAP.name)
    return _as_mapping(payload["frozen_measurements"], "frozen_measurements")


def _cert_r31() -> dict[str, object]:
    """Return the frozen CERT r3.1 @ 48-alert row."""
    return _as_mapping(
        _frozen_measurements()["cert_r31_at_48_alerts"],
        "frozen_measurements.cert_r31_at_48_alerts",
    )


def _cert_r42() -> dict[str, object]:
    """Return the frozen CERT r4.2 probe row."""
    return _as_mapping(
        _frozen_measurements()["cert_r42_probe"],
        "frozen_measurements.cert_r42_probe",
    )


class TestPublicCertRowRemains6B:
    @pytest.mark.lab_only
    def test_tracker_matches_adr_0032_literals(self) -> None:
        """JSON and ADR 0032 agree; neither may be rewritten to make :precision the headline."""
        row = _cert_r31()
        assert _as_str(row["headline_detector"], "headline_detector") == _PUBLIC_HEADLINE
        assert ":precision" not in _as_str(row["headline_detector"], "headline_detector")
        assert _as_float(row["precision_6b"], "precision_6b") == _PUBLIC_6B_PRECISION
        assert _as_int(row["true_positives_6b"], "true_positives_6b") == _PUBLIC_6B_TRUE_POSITIVES
        assert (
            _as_int(row["false_positives_6b"], "false_positives_6b") == _PUBLIC_6B_FALSE_POSITIVES
        )
        assert _as_float(row["window_recall"], "window_recall") == _PUBLIC_6B_WINDOW_RECALL
        assert _as_str(row["adr"], "adr") == "0032"

    def test_the_48_alert_budget_is_the_6b_counts(self) -> None:
        assert _PUBLIC_6B_TRUE_POSITIVES + _PUBLIC_6B_FALSE_POSITIVES == 48

    @pytest.mark.lab_only
    def test_precision_policy_at_48_is_a_loss_versus_6b(self) -> None:
        row = _cert_r31()
        policy = _as_float(row["precision_policy"], "precision_policy")
        public = _as_float(row["precision_6b"], "precision_6b")
        assert policy == _PRECISION_POLICY_AT_48
        assert public == _PUBLIC_6B_PRECISION
        assert policy < public
        assert _PRECISION_POLICY_AT_48 < _PUBLIC_6B_PRECISION
        notes = _as_str(row["notes"], "notes")
        assert "LOSS" in notes.upper()


class TestPrecisionPolicyIsNotThePublicRow:
    def test_log_suffix_remains_precision_and_identity_stays_blank(self) -> None:
        """``:precision`` is an experiment name. AggregationPolicy() is still the 6B scorer."""
        opted_in = precision_policy()
        identity = AggregationPolicy()
        assert opted_in.log_suffix == ":precision"
        assert identity.log_suffix == ""
        assert identity.log_tag == ""

    def test_identity_defaults_are_still_the_6b_no_ops(self) -> None:
        """Read-only pin. Does not construct a retuned policy as a new default."""
        identity = AggregationPolicy()
        assert identity.peer_match_factor == 1.0
        assert identity.min_out_of_band_families == 1
        assert identity.single_family_factor == 1.0
        assert identity.stem_weights == {}
        assert identity.feature_weights == {}
        assert identity.chronic_volume_halflife_days is None


class TestCertR42Probe:
    @pytest.mark.lab_only
    def test_peer_relative_positives_are_zero_and_events_are_not_on_disk(self) -> None:
        row = _cert_r42()
        assert _as_int(row["labelled_incidents"], "labelled_incidents") == 70
        assert _as_int(row["scenarios"], "scenarios") == 3
        assert (
            _as_int(row["scenario_3_compromised_vs_insider"], "scenario_3_compromised_vs_insider")
            == 10
        )
        assert _as_int(row["peer_relative_positives"], "peer_relative_positives") == 0
        assert _as_bool(row["events_on_disk"], "events_on_disk") is False
        assert _as_str(row["adr"], "adr") == "0023"


class TestCompetingHypothesisSet:
    def test_registered_ids_are_the_code_names_not_the_readme_aliases(self) -> None:
        ids = {template.template_id for template in sentiel_templates()}
        assert ids == _COMPETING_SET_IDS
        assert "legitimate_change" not in ids
        assert BENIGN_ROLE_CHANGE_TEMPLATE_ID == "benign_role_change"
        assert PEER_ANOMALY_TEMPLATE_ID == "peer_anomaly"
        assert COMPROMISED_ACCOUNT_TEMPLATE_ID == "compromised_account"
        assert INSIDER_MISUSE_TEMPLATE_ID == "insider_misuse"
        assert INSUFFICIENT_EVIDENCE_TEMPLATE_ID == "insufficient_evidence"


class TestHypothesisConfidenceIsUncalibrated:
    def test_the_caveat_constant_is_still_present_and_says_uncalibrated(self) -> None:
        assert "uncalibrated" in UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT.lower()
        assert "must not be surfaced" in UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT
        assert "§3.3" in UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT
        assert UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT in SENTIEL_VERTICAL_CAVEATS
        source = ENGINE_SRC.read_text(encoding="utf-8")
        assert "UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT" in source
        assert "uncalibrated" in source.lower()


class TestSentielHasNoProductSurface:
    def test_src_phos_sentiel_has_no_fastapi(self) -> None:
        hits: list[str] = []
        for path in sorted(SENTIEL_SRC.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            if "fastapi" in text.lower():
                hits.append(str(path.relative_to(REPO)))
        assert hits == []
