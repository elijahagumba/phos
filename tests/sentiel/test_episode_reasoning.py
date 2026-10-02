"""The first SEQUENCE_ANOMALY any PHOS engine has emitted, and the invariants it must not break."""

from datetime import UTC, datetime, timedelta

import pytest

from phos.ontology import EvidenceKind, InMemoryEvidenceStore
from phos.reasoning import INSUFFICIENT_EVIDENCE_TEMPLATE_ID
from phos.sentiel.episode_reasoning import (
    PATH_EVIDENCE_MARKER,
    SEQUENCE_EVIDENCE_MARKER,
    episode_library,
    explain_episode,
    path_evidence,
    sequence_evidence,
)
from phos.sentiel.episodes import Episode, EpisodePolicy, assemble_episodes
from phos.sentiel.paths import PathFindings
from phos.sentiel.sequence_scoring import SequenceScores
from phos.sentiel.templates import (
    COMPROMISED_ACCOUNT_TEMPLATE_ID,
    INSIDER_MISUSE_TEMPLATE_ID,
    sentiel_templates,
)

START = datetime(2010, 7, 1, tzinfo=UTC)
ENTITY = "ent_MALLORY9"


def _day(index: int) -> datetime:
    return START + timedelta(days=index)


def _episode(*rows: tuple[int, float]) -> Episode:
    return assemble_episodes(
        [(ENTITY, _day(index), score, ("ACCESS",), "logon_count") for index, score in rows],
        EpisodePolicy(anchor_threshold=5.0, extension_floor=1.0),
    )[0]


def _scores(population: float) -> SequenceScores:
    return SequenceScores(
        user_id="MALLORY9",
        population=population,
        count_baseline=1.0,
        n_tokens=6,
        alerts=True,
    )


def _findings(distant: int = 0, shared: int = 0) -> PathFindings:
    return PathFindings(
        user_id="MALLORY9",
        day=_day(0),
        internal_recipients=distant,
        distant_internal_recipients=distant,
        shared_device_distant=shared,
        max_hops=6,
        total_hops=6 * max(distant, 1),
    )


class TestTheOntologyMemberThatNothingEverEmitted:
    def test_a_rare_ordered_path_becomes_sequence_anomaly_evidence(self) -> None:
        evidence = sequence_evidence(ENTITY, _day(0), _scores(9.0), cut=5.0, weight=0.5)
        assert evidence is not None
        assert evidence.kind is EvidenceKind.SEQUENCE_ANOMALY
        assert evidence.source_id.startswith(SEQUENCE_EVIDENCE_MARKER)
        assert "surprise" in evidence.summary

    def test_a_day_below_the_cut_produces_nothing(self) -> None:
        assert sequence_evidence(ENTITY, _day(0), _scores(1.0), cut=5.0, weight=0.5) is None

    def test_the_summary_carries_the_order_blind_baseline_beside_the_ordered_one(self) -> None:
        """A sequence score that merely re-expresses volume must be visible as such."""
        evidence = sequence_evidence(ENTITY, _day(0), _scores(9.0), cut=5.0, weight=0.5)
        assert evidence is not None
        assert "ignoring order" in evidence.summary


class TestPathEvidence:
    def test_a_declared_path_finding_becomes_relationship_change_evidence(self) -> None:
        evidence = path_evidence(ENTITY, _day(0), _findings(distant=3), weight=0.5)
        assert evidence is not None
        assert evidence.kind is EvidenceKind.RELATIONSHIP_CHANGE
        assert evidence.source_id.startswith(PATH_EVIDENCE_MARKER)
        assert "outside this person's department" in evidence.summary

    def test_a_day_that_travelled_no_such_route_produces_nothing(self) -> None:
        assert path_evidence(ENTITY, _day(0), _findings(), weight=0.5) is None

    def test_an_undeclared_recipient_alone_does_not_raise_path_evidence(self) -> None:
        """external_email_count already measures it; one act must not raise a score twice."""
        findings = PathFindings(user_id="MALLORY9", day=_day(0), undeclared_recipients=5)
        assert path_evidence(ENTITY, _day(0), findings, weight=0.5) is None


class TestTheLibraryExtendsRatherThanForks:
    def test_ids_labels_and_priors_are_the_6c_library_untouched(self) -> None:
        original = {t.template_id: (t.label, t.prior) for t in sentiel_templates()}
        extended = {t.template_id: (t.label, t.prior) for t in episode_library().templates}
        assert extended == original

    def test_a_rare_order_supports_compromised_account_and_nothing_else(self) -> None:
        """A template supported by everything is separated from its rivals only by its prior."""
        supported = _supporting(EvidenceKind.SEQUENCE_ANOMALY)
        assert supported == {COMPROMISED_ACCOUNT_TEMPLATE_ID}

    def test_a_declared_path_supports_insider_misuse_and_nothing_else(self) -> None:
        supported = _supporting(EvidenceKind.RELATIONSHIP_CHANGE)
        assert supported == {INSIDER_MISUSE_TEMPLATE_ID}

    def test_neither_new_kind_is_listed_as_contradictory_anywhere(self) -> None:
        """Manufacturing a contradiction to tidy a ranking corrupts the belief arithmetic."""
        for template in episode_library().templates:
            for pattern in template.contradicted_by:
                assert EvidenceKind.SEQUENCE_ANOMALY not in pattern.kinds
                assert EvidenceKind.RELATIONSHIP_CHANGE not in pattern.kinds


def _supporting(kind: EvidenceKind) -> set[str]:
    return {
        template.template_id
        for template in episode_library().templates
        for pattern in template.supported_by
        if pattern.kinds == (kind,)
    }


class TestTheReasoningInvariantsHold:
    def test_every_registered_explanation_appears_including_untouched_ones(self) -> None:
        """A competing set with the unsupported explanations removed is a verdict."""
        store = InMemoryEvidenceStore()
        evidence = [sequence_evidence(ENTITY, _day(0), _scores(9.0), 5.0, 0.5)]
        narratives = explain_episode(_episode((0, 9.0)), [e for e in evidence if e], store)
        assert narratives
        template_ids = {
            store.get_hypothesis(hid).template_id  # type: ignore[union-attr]
            for hid in narratives[0].hypothesis_ids
        }
        assert template_ids == {t.template_id for t in sentiel_templates()}

    def test_the_residual_is_always_present(self) -> None:
        store = InMemoryEvidenceStore()
        evidence = [sequence_evidence(ENTITY, _day(0), _scores(9.0), 5.0, 0.5)]
        narratives = explain_episode(_episode((0, 9.0)), [e for e in evidence if e], store)
        labels = [
            store.get_hypothesis(hid).template_id  # type: ignore[union-attr]
            for hid in narratives[0].hypothesis_ids
        ]
        assert INSUFFICIENT_EVIDENCE_TEMPLATE_ID in labels

    def test_confidence_stays_bounded_and_overall_confidence_unset(self) -> None:
        store = InMemoryEvidenceStore()
        evidence = [
            sequence_evidence(ENTITY, _day(index), _scores(9.0), 5.0, 0.5) for index in range(3)
        ]
        narratives = explain_episode(
            _episode((0, 9.0), (1, 9.0), (2, 9.0)), [e for e in evidence if e], store
        )
        for narrative in narratives:
            assert narrative.overall_confidence is None
            for hid in narrative.hypothesis_ids:
                hypothesis = store.get_hypothesis(hid)
                assert hypothesis is not None
                assert 0.0 <= hypothesis.confidence <= 1.0

    def test_evidence_about_another_entity_is_refused(self) -> None:
        """A confidence built partly from somebody else's behaviour is ADR 0023's whole point."""
        store = InMemoryEvidenceStore()
        stray = sequence_evidence("ent_SOMEONE", _day(0), _scores(9.0), 5.0, 0.5)
        assert stray is not None
        with pytest.raises(ValueError, match="claim about somebody"):
            explain_episode(_episode((0, 9.0)), [stray], store)

    def test_evidence_ids_resolve_from_the_narrative_back_to_the_store(self) -> None:
        """Full traceability from episode to day to the fact underneath it."""
        store = InMemoryEvidenceStore()
        made = sequence_evidence(ENTITY, _day(0), _scores(9.0), 5.0, 0.5)
        assert made is not None
        store.add_evidence(made)
        narratives = explain_episode(_episode((0, 9.0)), [made], store)
        for evidence_id in narratives[0].evidence_ids:
            assert store.get_evidence(evidence_id) is not None
