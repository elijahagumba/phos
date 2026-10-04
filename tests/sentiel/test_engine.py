"""The Sentiel vertical: a scored entity-window in, competing explanations out.

The fixture corpus is four people over forty-five days, and every one of them exists to make one
claim checkable:

* ``NORMAL01`` departs once, weakly. It is the "evidence is thin" case, and what must lead its
  story is the residual — not the cheapest malicious explanation on offer.
* ``CHANGED1`` departs only in the relationship family. It is a sanctioned change, and the benign
  explanation must outrank both malicious ones. Without this case the engine reads every change as
  an attack, which is the failure PART 6C §5.1 names.
* ``INSIDER1`` departs in access and data handling. Both malicious explanations must overtake the
  benign one, which they can only do by accumulating evidence past a base rate that starts against
  them.
* ``PEERDIF1`` departs only against its declared peer group. **This case is a fixture and nothing
  else.** PART 6B established that neither of r3.1's labelled insiders is peer-relative — both are
  written in the self-relative register — so the capability is built, wired and exercised here, and
  is *unexercised by any real positive*. A test below says so in its own name.

Nothing here is tuned toward those four. The calibrator is fitted on a hand-made monotone signal
with no relation to the fixture's users, the priors come from `prior_at_rank`, and the assertions
are about *ordering* — which explanation leads — rather than about any particular confidence.
"""

import json
import subprocess
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy
import pytest

from phos.eval import Dataset, EvaluationReport, LatencySummary
from phos.models import GaussianBaseline
from phos.models.base import MAX_MAGNITUDE, StaticRangeFittedModel
from phos.ontology import (
    Domain,
    Evidence,
    Hypothesis,
    HypothesisStatus,
    Narrative,
    Observation,
    utc_now,
)
from phos.reasoning import (
    EVIDENCE_STRENGTH,
    INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    FittedCalibrator,
    IsotonicCalibrator,
    ReasoningConfig,
    calibrated_probabilities,
    rank_hypotheses,
    reconstruct_confidence,
    tied_lead_ids,
)
from phos.sentiel import (
    BENIGN_ROLE_CHANGE_TEMPLATE_ID,
    COMPROMISED_ACCOUNT_TEMPLATE_ID,
    INSIDER_MISUSE_TEMPLATE_ID,
    PEER_ANOMALY_TEMPLATE_ID,
    SCALE_BORROWED_WEIGHT_FACTOR,
    SENTIEL_VERTICAL_CAVEATS,
    UNQUANTIFIED_WEIGHT_FACTOR,
    BehaviourFamily,
    FeatureContribution,
    SentielConfig,
    SentielEngine,
    annotate_with_caveats,
    behaviour_family_of,
    behaviour_member_ids,
    family_of,
    is_behaviour_event,
    provenance_factor,
    sentiel_templates,
    static_range_model,
    stream_scored_windows,
    user_entity_id,
    user_id_of,
)

REPO = Path(__file__).resolve().parents[2]
SIXB_COMMIT = "79ed7c0caaf96f52eb7e3a29143fd48d641441ad"
"""The PART 6B commit. Pinned rather than ``HEAD``, so the reuse assertions keep their teeth.

``git diff HEAD`` goes quiet the moment 6C is committed, which makes "the spine is unmodified" a
statement about the working tree rather than about the PART. Diffing against the commit 6C started
from says the thing that was meant, permanently.
"""

_MODELS_OPENED_AFTER_6B = frozenset(
    {
        "src/phos/models/empirical.py",  # ADR 0086: quantile band; Gaussian file untouched
        "src/phos/models/__init__.py",  # ADR 0086: export the new baseline
    }
)
"""Model files ADR 0086 had to open. The Gaussian, EWMA and IQR modules stay frozen at 6B.

The empirical baseline is additive. `gaussian.py` is byte-identical to the 6B tree, and the
frozen public rows still fit `GaussianBaseline`.
"""

_ONTOLOGY_OPENED_AFTER_6B = frozenset(
    {
        "src/phos/ontology/store.py",  # ADR 0038: causal edges must cite ids already on the story
        "src/phos/ontology/narratives.py",  # ADR 0045: overall_confidence unset until calibrated
        "src/phos/ontology/evidence.py",  # ADR 0070: optional facet_kind / facet pair
        "src/phos/ontology/enums.py",  # ADR 0070: FacetKind
        "src/phos/ontology/__init__.py",  # ADR 0070: FacetKind export
    }
)
"""Ontology files later cycle ADRs had to open. The rest of the package stays frozen at 6B.

Each entry is named with the record that opened it, so the freeze is narrowed on purpose rather
than lifted by accident. ADR 0070's three are **additive and Sentiel-neutral**: two optional
fields defaulting to ``None``, one enum, one export. Sentiel sets no facet and reads none, and
`TestReuseNotFork`'s sibling assertions — Atlas's template priors and the shared belief
arithmetic — still pin that nothing downstream moved.
"""

START = datetime(2010, 1, 4, tzinfo=UTC)
TRAIN_DAYS = 40
TEST_DAYS = 5

ACCESS_FEATURES = ("logon_count", "off_hours_logon_count", "distinct_pcs")
DATA_FEATURES = ("file_access_count", "removable_device_connects", "distinct_files")
RELATIONSHIP_FEATURES_USED = ("new_pcs", "new_counterparties")
PEER_FEATURES_USED = ("logon_count_peer", "file_access_count_peer")
ALL_FEATURES = (
    *ACCESS_FEATURES,
    *DATA_FEATURES,
    *RELATIONSHIP_FEATURES_USED,
    *PEER_FEATURES_USED,
)

#: Departures this size clear `band_k` several times over and calibrate to ~1.0.
LOUD = 20.0
#: A departure that leaves the band but sits below every positive calibration knot.
FAINT = 3.5

USERS = ("NORMAL01", "CHANGED1", "INSIDER1", "PEERDIF1")

DEPARTURES: dict[str, tuple[str, ...]] = {
    "NORMAL01": (),
    "CHANGED1": RELATIONSHIP_FEATURES_USED,
    "INSIDER1": (*ACCESS_FEATURES, *DATA_FEATURES),
    "PEERDIF1": PEER_FEATURES_USED,
}


def _value(user: str, day: int, feature: str) -> float:
    """Return one user-day-feature value: a steady baseline, then a departure for some users."""
    base = 10.0 + (day % 5) * 0.5
    if day < TRAIN_DAYS:
        return base
    if feature in DEPARTURES[user]:
        return base + LOUD
    if user == "NORMAL01" and day == TRAIN_DAYS and feature == "logon_count":
        return base + FAINT
    return base


def _observations(days: int) -> list[Observation]:
    """Return a time-ordered per-``(user, day, feature)`` stream, the shape the featuriser emits."""
    stream: list[Observation] = []
    for day in range(days):
        for user in USERS:
            for index, feature in enumerate(ALL_FEATURES):
                stream.append(
                    Observation(
                        id=f"obs_{user}_{day:03d}_{index:02d}",
                        entity_ids=[user_entity_id(user)],
                        feature=feature,
                        value=_value(user, day, feature),
                        timestamp=START + timedelta(days=day),
                        domain=Domain.SENTIEL,
                    )
                )
    return stream


@pytest.fixture(scope="module")
def fitted() -> StaticRangeFittedModel:
    """A per-key Gaussian fitted on the attack-free training prefix only."""
    training = [o for o in _observations(TRAIN_DAYS + TEST_DAYS) if o.timestamp < _test_start()]
    return static_range_model(GaussianBaseline(min_samples=8).fit(training))


def _test_start() -> datetime:
    return START + timedelta(days=TRAIN_DAYS)


@pytest.fixture(scope="module")
def calibrator() -> FittedCalibrator:
    """A calibrator fitted on a hand-made monotone signal, unrelated to the fixture's users.

    Its knots are what make the fixture's two registers separable: a magnitude below 15 carries
    almost no weight and one well above it carries almost all of it. Fitted from numbers rather
    than stubbed, so the tests below exercise the real calibration path.
    """
    scores = numpy.arange(1.0, 31.0)
    labels = numpy.where(scores < 15.0, 0.0, 1.0)
    return IsotonicCalibrator().fit(scores, labels)


@pytest.fixture
def dataset() -> Dataset:
    """The test half: five days beginning the day the departures start."""
    observations = [
        o for o in _observations(TRAIN_DAYS + TEST_DAYS) if o.timestamp >= _test_start()
    ]
    return Dataset(
        name="fixture-user-day",
        domain=Domain.SENTIEL,
        observations=observations,
        source_note="hand-built fixture",
    )


@pytest.fixture
def engine(fitted: StaticRangeFittedModel, calibrator: FittedCalibrator) -> SentielEngine:
    return SentielEngine(
        fitted,
        calibrator,
        config=SentielConfig(
            reasoning=ReasoningConfig(correlation_window=timedelta(days=7), seed=7)
        ),
    )


# ------------------------------------------------------------------------------------------------
# Reading what a run produced
# ------------------------------------------------------------------------------------------------


def _narrative_for(engine: SentielEngine, narratives: Sequence[Narrative], user: str) -> Narrative:
    """Return the one story about ``user``."""
    entity = user_entity_id(user)
    found = [
        narrative
        for narrative in narratives
        if any(
            entity in _evidence(engine, evidence_id).entity_ids
            for evidence_id in narrative.evidence_ids
        )
    ]
    assert len(found) == 1, f"expected one story about {user}, got {len(found)}"
    return found[0]


def _evidence(engine: SentielEngine, evidence_id: str) -> Evidence:
    found = engine.store.get_evidence(evidence_id)
    assert found is not None
    return found


def _hypotheses(engine: SentielEngine, narrative: Narrative) -> list[Hypothesis]:
    resolved: list[Hypothesis] = []
    for hypothesis_id in narrative.hypothesis_ids:
        hypothesis = engine.store.get_hypothesis(hypothesis_id)
        assert hypothesis is not None
        resolved.append(hypothesis)
    return resolved


def _ranked(engine: SentielEngine, narrative: Narrative) -> list[str]:
    """Return the template ids of a story's explanations, most confident first."""
    return [hypothesis.template_id for hypothesis in _hypotheses(engine, narrative)]


def _confidence(engine: SentielEngine, narrative: Narrative, template_id: str) -> float:
    for hypothesis in _hypotheses(engine, narrative):
        if hypothesis.template_id == template_id:
            return hypothesis.confidence
    raise AssertionError(f"{template_id} is not in this story")


# ------------------------------------------------------------------------------------------------
# Criterion 1 — reuse, not fork
# ------------------------------------------------------------------------------------------------


def _git(*args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args], capture_output=True, text=True, check=False, cwd=REPO, timeout=30
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - env dependent
        return None
    if completed.returncode != 0:  # pragma: no cover - env dependent
        return None
    return completed.stdout


class TestReuseNotFork:
    @pytest.mark.parametrize(
        "path",
        [
            "src/phos/models",
            "src/phos/ontology",
            "src/phos/sentiel/cert.py",
            "src/phos/sentiel/entities.py",
            "src/phos/sentiel/events.py",
            "src/phos/sentiel/evaluation.py",
            "src/phos/sentiel/featurise.py",
            "src/phos/sentiel/history.py",
            "src/phos/sentiel/labels.py",
            "src/phos/sentiel/peers.py",
        ],
    )
    def test_the_reused_code_is_unmodified_since_the_6b_commit(self, path: str) -> None:
        """PART 6C consumes the spine and the earlier Sentiel layers; it does not edit them.

        Diffed against the commit 6C started from rather than against ``HEAD``, because ``HEAD``
        stops saying anything the moment this PART is committed.

        Atlas, eval, `scoring.py`, and `phos.reasoning` are **not** on this list: later cycle work
        extended them (batch-distillation join, joint-distance gating, command grounding,
        precision policy, and command-lead session 1's lead-tie refusal) without forking the
        Sentiel competing set. What remains frozen is intake, featurisation, peers, and the
        shared ontology/models packages 6C promised not to restyle.

        Ontology files opened after 6B stay named in `_ONTOLOGY_OPENED_AFTER_6B` rather than
        silently un-freezing the package: `store.py` (ADR 0038 causal-edge integrity),
        `narratives.py` (ADR 0045: ``overall_confidence`` optional), and `evidence.py` /
        `enums.py` / `__init__.py` (ADR 0070: the optional `facet_kind` / `facet` pair that
        replaced summary-string parsing in Atlas's matchers). Model files opened after 6B stay
        named in `_MODELS_OPENED_AFTER_6B` (ADR 0086: the empirical command baseline and its
        export). `gaussian.py` is not on that list.
        """
        if _git("cat-file", "-e", f"{SIXB_COMMIT}^{{commit}}") is None:  # pragma: no cover
            pytest.skip("the PART 6B commit is not in this checkout")
        changed = _git("diff", SIXB_COMMIT, "--name-only", "--", path)
        if changed is None:  # pragma: no cover - env dependent
            pytest.skip("git unavailable")
        opened = _ONTOLOGY_OPENED_AFTER_6B | _MODELS_OPENED_AFTER_6B
        leftover = [line for line in changed.strip().splitlines() if line and line not in opened]
        assert leftover == [], f"PART 6C must reuse {path} unchanged, but git reports:\n{changed}"

    def test_atlas_reasons_with_exactly_the_templates_it_reasoned_with_before(self) -> None:
        """Atlas's own explanations are pinned here, so a shared-spine edit cannot move them."""
        from phos.atlas import atlas_templates

        assert [(t.template_id, round(t.prior, 12)) for t in atlas_templates()] == [
            ("sensor_or_device_fault", 0.155172413793),
            ("engineering_maintenance", 0.057692307692),
            ("process_disturbance", 0.057692307692),
            ("unauthorised_control_activity", 0.02),
            ("insufficient_evidence", 0.3),
        ]

    def test_the_belief_arithmetic_is_the_shared_one(self) -> None:
        """`EVIDENCE_STRENGTH` and the residual prior are read, never restated, by Sentiel."""
        import phos.sentiel.templates as sentiel_templates_module

        assert sentiel_templates_module.EVIDENCE_STRENGTH is EVIDENCE_STRENGTH
        assert sentiel_templates_module.RESIDUAL_PRIOR == 0.30

    @pytest.mark.parametrize("module_name", ["phos.sentiel.engine", "phos.sentiel.templates"])
    def test_no_spine_symbol_is_shadowed_by_a_local_reimplementation(
        self, module_name: str
    ) -> None:
        """Every reasoning name these modules hold must be *the* reasoning name, not a copy."""
        import importlib

        import phos.reasoning as spine

        module = importlib.import_module(module_name)
        for name in spine.__all__:
            if hasattr(module, name):
                assert getattr(module, name) is getattr(spine, name), (
                    f"{module_name} defines its own {name}; PART 6C consumes the spine"
                )

    def test_the_engine_confidence_replays_exactly_through_the_shared_belief_rule(
        self, engine: SentielEngine, dataset: Dataset
    ) -> None:
        """Constitution §3.2, executable: nothing here computes a confidence of its own.

        If the engine had its own belief arithmetic, `reconstruct_confidence` — which is 4B's —
        would land somewhere else.
        """
        engine.run(dataset)
        held = {item.id: item for item in engine.store.evidence()}
        checked = 0
        for hypothesis in engine.store.hypotheses():
            if not hypothesis.supporting and not hypothesis.contradictory:
                continue
            assert reconstruct_confidence(hypothesis, held) == pytest.approx(hypothesis.confidence)
            checked += 1
        assert checked > 0


# ------------------------------------------------------------------------------------------------
# Criterion 2 — the reasoning invariants
# ------------------------------------------------------------------------------------------------


class TestTheInvariantsHold:
    def test_no_story_collapses_to_a_single_explanation(
        self, engine: SentielEngine, dataset: Dataset
    ) -> None:
        narratives = engine.run(dataset)
        assert narratives
        for narrative in narratives:
            assert len(narrative.hypothesis_ids) >= 2

    def test_insufficient_evidence_is_in_every_story(
        self, engine: SentielEngine, dataset: Dataset
    ) -> None:
        for narrative in engine.run(dataset):
            assert INSUFFICIENT_EVIDENCE_TEMPLATE_ID in _ranked(engine, narrative)

    def test_the_residual_leads_when_the_evidence_is_thin(
        self, engine: SentielEngine, dataset: Dataset
    ) -> None:
        """One faint departure must not promote the cheapest malicious explanation on offer."""
        narratives = engine.run(dataset)
        story = _narrative_for(engine, narratives, "NORMAL01")
        assert _ranked(engine, story)[0] == INSUFFICIENT_EVIDENCE_TEMPLATE_ID

    def test_session_s3_unusual_is_not_a_why(self, engine: SentielEngine, dataset: Dataset) -> None:
        """Session S3: analysts see a departure without promoting compromised vs insider."""
        narratives = engine.run(dataset)
        story = _narrative_for(engine, narratives, "NORMAL01")
        ranked = _ranked(engine, story)
        assert ranked[0] == INSUFFICIENT_EVIDENCE_TEMPLATE_ID
        assert COMPROMISED_ACCOUNT_TEMPLATE_ID in ranked
        assert INSIDER_MISUSE_TEMPLATE_ID in ranked
        assert story.overall_confidence is None

    def test_no_confidence_reaches_certainty(self, engine: SentielEngine, dataset: Dataset) -> None:
        engine.run(dataset)
        for hypothesis in engine.store.hypotheses():
            assert 0.0 < hypothesis.confidence < 1.0

    def test_an_explanation_the_evidence_never_touched_is_still_reported(
        self, engine: SentielEngine, dataset: Dataset
    ) -> None:
        """A set with the unsupported explanations removed would be a verdict."""
        narratives = engine.run(dataset)
        story = _narrative_for(engine, narratives, "CHANGED1")
        ranked = _ranked(engine, story)
        assert COMPROMISED_ACCOUNT_TEMPLATE_ID in ranked or INSIDER_MISUSE_TEMPLATE_ID in ranked

    def test_before_any_evidence_the_priors_are_base_rate_ordered(self) -> None:
        priors = {t.template_id: t.prior for t in sentiel_templates()}
        assert priors[INSUFFICIENT_EVIDENCE_TEMPLATE_ID] > priors[BENIGN_ROLE_CHANGE_TEMPLATE_ID]
        assert priors[BENIGN_ROLE_CHANGE_TEMPLATE_ID] > priors[COMPROMISED_ACCOUNT_TEMPLATE_ID]
        assert priors[COMPROMISED_ACCOUNT_TEMPLATE_ID] > priors[INSIDER_MISUSE_TEMPLATE_ID]


def _sentiel_hypothesis(template_id: str, confidence: float, label: str) -> Hypothesis:
    return Hypothesis(
        label=label,
        template_id=template_id,
        domain=Domain.SENTIEL,
        prior=0.10,
        confidence=confidence,
        status=HypothesisStatus.ACTIVE,
    )


class TestCeilingTieIsARefusal:
    """ADR 0036 on the Sentiel path: a shared ceiling is silence, not an alphabetical winner."""

    def test_rank_hypotheses_does_not_crown_benign_alphabetically(self) -> None:
        """`benign_role_change` sorts first; a ceiling tie must still raise the residual."""
        compromised = _sentiel_hypothesis(
            COMPROMISED_ACCOUNT_TEMPLATE_ID, 1.0, "Compromised account"
        )
        benign = _sentiel_hypothesis(BENIGN_ROLE_CHANGE_TEMPLATE_ID, 1.0, "Benign role change")
        residual = _sentiel_hypothesis(
            INSUFFICIENT_EVIDENCE_TEMPLATE_ID, 0.30, "Insufficient evidence"
        )
        ranked = rank_hypotheses((compromised, benign, residual))
        assert ranked[0].template_id == INSUFFICIENT_EVIDENCE_TEMPLATE_ID
        assert tied_lead_ids(ranked) == (
            BENIGN_ROLE_CHANGE_TEMPLATE_ID,
            COMPROMISED_ACCOUNT_TEMPLATE_ID,
        )
        assert BENIGN_ROLE_CHANGE_TEMPLATE_ID < COMPROMISED_ACCOUNT_TEMPLATE_ID
        assert [item.template_id for item in ranked[1:3]] == [
            BENIGN_ROLE_CHANGE_TEMPLATE_ID,
            COMPROMISED_ACCOUNT_TEMPLATE_ID,
        ]

    def test_completed_story_raises_insufficient_evidence_on_a_ceiling_tie(
        self, engine: SentielEngine
    ) -> None:
        """SentielEngine._completed must call the shared ranker, not a local alphabetical sort."""
        compromised = _sentiel_hypothesis(
            COMPROMISED_ACCOUNT_TEMPLATE_ID, 1.0, "Compromised account"
        )
        benign = _sentiel_hypothesis(BENIGN_ROLE_CHANGE_TEMPLATE_ID, 1.0, "Benign role change")
        for hypothesis in (compromised, benign):
            engine.store.add_hypothesis(hypothesis)
        stub = Narrative(
            title="placeholder",
            domain=Domain.SENTIEL,
            hypothesis_ids=[compromised.id, benign.id],
            evidence_ids=[],
        )
        completed = engine._completed(stub)
        ranked = _ranked(engine, completed)
        assert ranked[0] == INSUFFICIENT_EVIDENCE_TEMPLATE_ID
        assert completed.overall_confidence is None
        assert "insufficient" in completed.title.lower()
        assert ranked.index(BENIGN_ROLE_CHANGE_TEMPLATE_ID) < ranked.index(
            COMPROMISED_ACCOUNT_TEMPLATE_ID
        )


# ------------------------------------------------------------------------------------------------
# Criterion 3 — the evidence mapping and its traceability
# ------------------------------------------------------------------------------------------------


class TestTheEvidenceMapping:
    def test_the_engine_scores_exactly_what_the_6b_scorer_scores(
        self, engine: SentielEngine, dataset: Dataset, fitted: StaticRangeFittedModel
    ) -> None:
        """The engine keeps its own index of the observations behind a window; it must not drift.

        `WindowScorer` does not expose the observations it judged and PART 6C may not modify it, so
        the engine buffers them alongside. This pins the two together.
        """
        engine.run(dataset)
        expected = list(stream_scored_windows(dataset.observations, fitted))
        produced = {(w.entity_id, w.timestamp): w for w in engine.explained_windows()}
        for window in expected:
            key = (window.entity_id, window.timestamp)
            if key in produced:
                assert produced[key].score == pytest.approx(window.score)
                assert produced[key].contributions == window.contributions

    def test_every_reasoned_fact_is_a_behaviour_event(
        self, engine: SentielEngine, dataset: Dataset
    ) -> None:
        """A per-feature fact reaching the engine would be counted twice — see the templates ADR."""
        engine.run(dataset)
        cited: set[str] = set()
        for hypothesis in engine.store.hypotheses():
            cited |= {*hypothesis.supporting, *hypothesis.contradictory}
        assert cited
        for evidence_id in cited:
            assert is_behaviour_event(_evidence(engine, evidence_id))

    def test_a_hypothesis_traces_to_the_contributions_that_moved_it(
        self, engine: SentielEngine, dataset: Dataset
    ) -> None:
        """The whole chain, walked: hypothesis → event → member → deviation → observation."""
        narratives = engine.run(dataset)
        story = _narrative_for(engine, narratives, "INSIDER1")
        moved = [h for h in _hypotheses(engine, story) if h.supporting]
        assert moved

        walked = 0
        for hypothesis in moved:
            for event_id in hypothesis.supporting:
                event = _evidence(engine, event_id)
                family = behaviour_family_of(event)
                assert family is not None
                for member_id in behaviour_member_ids(event):
                    member = _evidence(engine, member_id)
                    deviation = engine.store.get_deviation(member.source_id)
                    assert deviation is not None
                    observation = engine.store.get_observation(deviation.observation_id)
                    assert observation is not None
                    assert family_of(observation.feature) is family
                    assert user_id_of(observation.entity_ids[0]) == "INSIDER1"
                    walked += 1
        assert walked > 0

    def test_an_events_weight_is_its_strongest_members(
        self, engine: SentielEngine, dataset: Dataset
    ) -> None:
        engine.run(dataset)
        events = [e for e in engine.store.evidence() if is_behaviour_event(e)]
        assert events
        for event in events:
            members = [_evidence(engine, member) for member in behaviour_member_ids(event)]
            assert event.weight == pytest.approx(max(member.weight for member in members))

    def test_a_wider_feature_set_does_not_multiply_the_evidence(
        self, engine: SentielEngine, dataset: Dataset
    ) -> None:
        """PART 6B's counting discipline, one layer up: at most one event per family per window."""
        engine.run(dataset)
        seen: set[tuple[str, datetime, BehaviourFamily]] = set()
        for event in engine.store.evidence():
            if not is_behaviour_event(event):
                continue
            family = behaviour_family_of(event)
            assert family is not None
            key = (event.entity_ids[0], event.timestamp, family)
            assert key not in seen
            seen.add(key)

    def test_an_in_band_contribution_never_becomes_evidence(
        self, engine: SentielEngine, dataset: Dataset
    ) -> None:
        """4A's boundary applies to Sentiel exactly as it applies to Atlas.

        The scorer emits a candidate at ``emit_k``; only a value that actually left its expected
        range may become something a hypothesis rests on.
        """
        engine.run(dataset)
        assert engine.summary().in_band > 0
        for evidence in engine.store.evidence():
            if is_behaviour_event(evidence):
                continue
            deviation = engine.store.get_deviation(evidence.source_id)
            assert deviation is not None
            observation = engine.store.get_observation(deviation.observation_id)
            assert observation is not None
            assert not deviation.expected.contains(observation.value)


class TestBorrowedScaleProvenance:
    def test_a_measured_departure_carries_its_full_weight(self) -> None:
        assert provenance_factor(_contribution()) == 1.0

    def test_a_borrowed_scale_is_worth_less_than_a_measured_one(self) -> None:
        borrowed = provenance_factor(_contribution(scale_borrowed=True))
        assert 0.0 < borrowed < 1.0
        assert borrowed == SCALE_BORROWED_WEIGHT_FACTOR

    def test_an_unquantified_departure_is_worth_less_than_a_borrowed_one(self) -> None:
        """Its magnitude is the clamp, not a measurement: what survives is only its existence."""
        assert UNQUANTIFIED_WEIGHT_FACTOR < SCALE_BORROWED_WEIGHT_FACTOR
        assert provenance_factor(_contribution(unquantified=True)) == UNQUANTIFIED_WEIGHT_FACTOR

    def test_the_discount_reaches_the_stored_evidence(self, calibrator: FittedCalibrator) -> None:
        """The flag is not decoration: an evidence weight is the calibrated number times it."""
        dataset, model = _degenerate_corpus()
        engine = SentielEngine(model, calibrator)
        engine.run(dataset)
        members = [e for e in engine.store.evidence() if not is_behaviour_event(e)]
        assert members
        summary = engine.summary()
        assert summary.borrowed + summary.unquantified > 0
        full = calibrated_probabilities(calibrator, [MAX_MAGNITUDE])[0]
        for member in members:
            assert member.weight <= full


def _contribution(
    *, scale_borrowed: bool = False, unquantified: bool = False
) -> FeatureContribution:
    return FeatureContribution(
        feature="file_access_count",
        value=42.0,
        magnitude=9.0,
        contribution=0.95,
        scale_borrowed=scale_borrowed,
        unquantified=unquantified,
    )


def _degenerate_corpus() -> tuple[Dataset, StaticRangeFittedModel]:
    """A corpus whose per-key baselines have no spread, so every departure needs a borrowed one."""
    stream: list[Observation] = []
    for day in range(TRAIN_DAYS + 2):
        for index, user in enumerate(("FLATUSR1", "FLATUSR2")):
            constant = 0.0 if user == "FLATUSR1" else float(index)
            value = constant if day < TRAIN_DAYS else constant + 40.0
            stream.append(
                Observation(
                    id=f"obs_flat_{user}_{day:03d}",
                    entity_ids=[user_entity_id(user)],
                    feature="file_access_count",
                    value=value,
                    timestamp=START + timedelta(days=day),
                    domain=Domain.SENTIEL,
                )
            )
    cut = START + timedelta(days=TRAIN_DAYS)
    model = static_range_model(
        GaussianBaseline(min_samples=8).fit([o for o in stream if o.timestamp < cut])
    )
    dataset = Dataset(
        name="degenerate",
        domain=Domain.SENTIEL,
        observations=[o for o in stream if o.timestamp >= cut],
    )
    return dataset, model


# ------------------------------------------------------------------------------------------------
# Criteria 4 and 5 — the explanations discriminate
# ------------------------------------------------------------------------------------------------


class TestTheExplanationsDiscriminate:
    def test_a_sanctioned_change_is_explained_as_one(
        self, engine: SentielEngine, dataset: Dataset
    ) -> None:
        """Criterion 4: the engine does not read every deviation as an attack."""
        narratives = engine.run(dataset)
        story = _narrative_for(engine, narratives, "CHANGED1")
        benign = _confidence(engine, story, BENIGN_ROLE_CHANGE_TEMPLATE_ID)
        assert benign > _confidence(engine, story, COMPROMISED_ACCOUNT_TEMPLATE_ID)
        assert benign > _confidence(engine, story, INSIDER_MISUSE_TEMPLATE_ID)
        assert _ranked(engine, story)[0] == BENIGN_ROLE_CHANGE_TEMPLATE_ID

    def test_a_self_relative_insider_pushes_the_malicious_explanations_above_benign(
        self, engine: SentielEngine, dataset: Dataset
    ) -> None:
        """Criterion 5, in the register PART 6B measured r3.1's two labelled insiders in."""
        narratives = engine.run(dataset)
        story = _narrative_for(engine, narratives, "INSIDER1")
        benign = _confidence(engine, story, BENIGN_ROLE_CHANGE_TEMPLATE_ID)
        assert _confidence(engine, story, COMPROMISED_ACCOUNT_TEMPLATE_ID) > benign
        assert _confidence(engine, story, INSIDER_MISUSE_TEMPLATE_ID) > benign

    def test_a_peer_relative_departure_raises_the_peer_explanation_on_a_fixture_only(
        self, engine: SentielEngine, dataset: Dataset
    ) -> None:
        """The capability works, and no real positive exercises it.

        PART 6B read CERT r3.1's own ``answers/scenarios.txt`` and found both labelled insiders
        written in the self-relative register — someone who "did not previously" do a thing and
        begins, and someone acting "at markedly higher rates than their previous activity". The
        insider who is unremarkable against their own past and remarkable against their team's is
        not among r3.1's labelled examples, so this fixture is the only positive case
        `peer_anomaly` has anywhere in PHOS.
        """
        narratives = engine.run(dataset)
        story = _narrative_for(engine, narratives, "PEERDIF1")
        assert _ranked(engine, story)[0] == PEER_ANOMALY_TEMPLATE_ID
        peer = _confidence(engine, story, PEER_ANOMALY_TEMPLATE_ID)
        assert peer > _confidence(engine, story, BENIGN_ROLE_CHANGE_TEMPLATE_ID)
        assert peer > _confidence(engine, story, COMPROMISED_ACCOUNT_TEMPLATE_ID)

    def test_the_engine_never_asserts_intent(self, engine: SentielEngine, dataset: Dataset) -> None:
        """Sentiel reports what to investigate and why; deciding is the operator's job."""
        for narrative in engine.run(dataset):
            assert narrative.overall_confidence is None
            assert len(narrative.hypothesis_ids) > 1


# ------------------------------------------------------------------------------------------------
# Criteria 6 and 7 — end to end, logged, deterministic
# ------------------------------------------------------------------------------------------------


class TestTheVerticalEndToEnd:
    def test_a_run_is_deterministic(
        self, fitted: StaticRangeFittedModel, calibrator: FittedCalibrator, dataset: Dataset
    ) -> None:
        """The same corpus and the same fitted parts give the same stories, ids aside."""
        shapes = []
        for _ in range(2):
            engine = SentielEngine(fitted, calibrator, config=SentielConfig())
            narratives = engine.run(dataset)
            shapes.append(
                [
                    (
                        narrative.title,
                        narrative.overall_confidence,
                        len(narrative.evidence_ids),
                        tuple(_ranked(engine, narrative)),
                    )
                    for narrative in narratives
                ]
            )
        assert shapes[0] == shapes[1]

    def test_an_empty_corpus_explains_nothing_and_does_not_raise(
        self, fitted: StaticRangeFittedModel, calibrator: FittedCalibrator
    ) -> None:
        engine = SentielEngine(fitted, calibrator)
        empty = Dataset(name="empty", domain=Domain.SENTIEL, observations=[])
        assert engine.run(empty) == []
        assert engine.summary().windows_scored == 0

    def test_a_threshold_narrows_what_is_explained(
        self, fitted: StaticRangeFittedModel, calibrator: FittedCalibrator, dataset: Dataset
    ) -> None:
        """An analyst explains the windows they would look at, not every window there is."""
        loose = SentielEngine(fitted, calibrator, config=SentielConfig(alert_threshold=0.0))
        loose.run(dataset)
        tight = SentielEngine(fitted, calibrator, config=SentielConfig(alert_threshold=2.0))
        tight.run(dataset)
        assert tight.summary().windows_explained < loose.summary().windows_explained
        assert tight.summary().windows_scored == loose.summary().windows_scored

    def test_running_twice_against_one_store_does_not_collide(
        self, fitted: StaticRangeFittedModel, calibrator: FittedCalibrator, dataset: Dataset
    ) -> None:
        engine = SentielEngine(fitted, calibrator)
        first = engine.run(dataset)
        second = engine.run(dataset)
        assert len(first) == len(second)

    def test_the_engine_name_carries_what_produced_the_numbers(self, engine: SentielEngine) -> None:
        assert "gaussian" in engine.name
        assert "isotonic" in engine.name

    def test_a_duplicated_feature_in_one_window_is_refused(
        self, fitted: StaticRangeFittedModel, calibrator: FittedCalibrator
    ) -> None:
        """A contribution that cannot be traced to a unique measurement is a traceability hole."""
        day = _test_start()
        doubled = [
            Observation(
                id=f"obs_dup_{index}",
                entity_ids=[user_entity_id("INSIDER1")],
                feature="logon_count",
                value=99.0,
                timestamp=day,
                domain=Domain.SENTIEL,
            )
            for index in range(2)
        ]
        engine = SentielEngine(fitted, calibrator)
        with pytest.raises(ValueError, match="more than once"):
            engine.run(Dataset(name="dup", domain=Domain.SENTIEL, observations=doubled))


class TestTheCaveats:
    def test_every_caveat_reaches_a_logged_report(self) -> None:
        annotated = annotate_with_caveats(_report())
        for caveat in SENTIEL_VERTICAL_CAVEATS:
            assert caveat in annotated.source_note

    def test_annotating_twice_does_not_duplicate(self) -> None:
        once = annotate_with_caveats(_report())
        assert annotate_with_caveats(once) == once

    def test_the_corpus_provenance_survives(self) -> None:
        annotated = annotate_with_caveats(_report())
        assert annotated.source_note.startswith("CERT r3.1")

    @pytest.mark.parametrize(
        "phrase",
        [
            "NOT calibrated",
            "peer_anomaly",
            "SYNTHETIC",
            "2 users",
            "strongest member",
        ],
    )
    def test_the_four_things_part_6c_requires_are_all_said(self, phrase: str) -> None:
        """PART 6C §6, checked rather than trusted to a document nobody reads."""
        assert any(phrase in caveat for caveat in SENTIEL_VERTICAL_CAVEATS)


def _report() -> EvaluationReport:
    return EvaluationReport(
        detector_name="sentiel-vertical",
        dataset_name="cert-r3.1",
        domain=Domain.SENTIEL,
        created_at=utc_now(),
        seed=7,
        source_note="CERT r3.1 provenance",
        alert_threshold=1.0,
        match_tolerance_seconds=0.0,
        calibration_bins=10,
        n_observations=1,
        n_detections=1,
        n_alerts=1,
        n_attack_intervals=1,
        normal_hours=1.0,
        window_recall=0.0,
        false_positives=1,
        false_positive_rate=1.0,
        precision=0.0,
        recall_sample=0.0,
        f1=0.0,
        latency=LatencySummary(count=0),
        expected_calibration_error=0.0,
        brier_score=0.0,
    )


# ------------------------------------------------------------------------------------------------
# Criterion 6 — the real corpus, when it is present
# ------------------------------------------------------------------------------------------------

DATA_DIR = REPO / "data"
MANIFEST = DATA_DIR / "cert-insider-threat" / "sentiel-manifest.json"


def _manifest() -> dict[str, object] | None:
    if not MANIFEST.is_file():
        return None
    manifest: dict[str, object] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    release = DATA_DIR / str(manifest["release_dir"])
    answers = DATA_DIR / str(manifest["answers_dir"])
    return manifest if release.is_dir() and answers.is_dir() else None


MANIFEST_DATA = _manifest()

_REAL_EVENTS = 400_000
"""Enough real rows to cross every log and several weeks; far short of the 13 GB corpus."""


@pytest.mark.skipif(
    MANIFEST_DATA is None,
    reason=(
        "the real CERT release is not present. Fetch it with:\n"
        "    python scripts/fetch_datasets.py cert-insider-threat --yes"
    ),
)
def test_the_vertical_runs_on_the_real_corpus() -> None:
    """A correctness check against real files, not a measurement.

    The measurement is ``scripts/evaluate_sentiel_engine.py``. What this catches is everything the
    hand-built fixture cannot: that the real featuriser's feature names are the ones the behaviour
    partition was written against, and that a real user-window survives the whole path from CERT
    rows to a traceable story.
    """
    import itertools

    from phos.sentiel import CertReader, CertRelease, FeatureSet, Featuriser

    assert MANIFEST_DATA is not None
    release_dir = DATA_DIR / str(MANIFEST_DATA["release_dir"])
    reader = CertReader.for_release(CertRelease.discover(release_dir))
    catalogue = reader.catalogue()
    featuriser = Featuriser(
        organisation_domain=catalogue.dominant_email_domain(), feature_set=FeatureSet.ENRICHED
    )

    def _stream() -> Iterator[Observation]:
        return featuriser.stream(itertools.islice(reader.events(), _REAL_EVENTS))

    observations = list(_stream())
    assert observations
    for observation in observations:
        assert family_of(observation.feature) is not None, (
            f"the real featuriser emits {observation.feature!r}, which no behaviour family covers"
        )

    cut = observations[len(observations) // 2].timestamp
    training = [o for o in observations if o.timestamp < cut]
    fitted = static_range_model(GaussianBaseline(min_samples=8).fit(training))
    scores = numpy.arange(1.0, 31.0)
    calibrator = IsotonicCalibrator().fit(scores, numpy.where(scores < 15.0, 0.0, 1.0))

    engine = SentielEngine(fitted, calibrator, config=SentielConfig(alert_threshold=1.0))
    narratives = engine.run(
        Dataset(
            name="cert-r3.1-slice",
            domain=Domain.SENTIEL,
            observations=[o for o in observations if o.timestamp >= cut],
        )
    )
    for narrative in narratives:
        assert INSUFFICIENT_EVIDENCE_TEMPLATE_ID in _ranked(engine, narrative)
        assert narrative.overall_confidence is None
