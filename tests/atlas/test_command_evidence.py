"""Tests for the seam where command behaviour becomes something reasoning may weigh.

Three claims are under test, and they are different in kind.

**The path is the existing one.** A command-behaviour departure must arrive at the reasoning engine
as the same `Evidence` a sensor departure does — same kind, same calibrated weight, same
traceability — because a second evidence format would be a second ontology (Constitution §3.1). The
tests assert the shape of what comes out and walk the whole chain back to a frame range in a
capture file.

**The refusals are the point.** A structural change of zero, a finding whose feature nothing here
recognises, and the two evidence streams crossed with each other are all things that would produce
a plausible-looking number from nothing.

**The discrimination is measured, not asserted.** The last section builds a fixture where sensor
evidence alone leaves the benign explanation ahead, adds one command-graph finding, and checks the
ordering flips — with the log-odds arithmetic computed by hand beside it, so the test says *why*
rather than only *that*.
"""

import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from phos.atlas import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    PROCESS_DISTURBANCE_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
    atlas_library,
)
from phos.atlas.command_evidence import (
    COMMAND_EVIDENCE_CAVEATS,
    GRAPH_FINDING_MARKER,
    UNGROUPED_COMMAND_EVIDENCE_CAVEAT,
    UNMEASURED_COMMAND_DETECTION_CAVEAT,
    CommandEvidence,
    graph_finding_feature_of,
    graph_finding_marker,
    promote_command_behaviour,
    promote_graph_findings,
)
from phos.atlas.packet import (
    COMMAND_COUNT,
    SILENT_COMMAND_RELATIONSHIP,
    UNEXPECTED_COMMAND_FUNCTION,
    UNKNOWN_COMMAND_RELATIONSHIP,
)
from phos.models import GaussianBaseline
from phos.ontology import (
    Domain,
    Evidence,
    EvidenceKind,
    EvidenceRole,
    InMemoryEvidenceStore,
    Observation,
)
from phos.reasoning import (
    EVIDENCE_STRENGTH,
    INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    FittedPlattCalibrator,
    ReasoningConfig,
    ReasoningEngine,
)

EPOCH = datetime(2026, 8, 14, 9, 0, tzinfo=UTC)
DEVICE = "ent_10.0.0.9"
TARGET = "ent_10.0.0.20"
POLLER = "ent_10.0.0.30"
OTHER_PLC = "ent_10.0.0.40"
CAPTURE = "/captures/plant.pcap"
WINDOW = timedelta(minutes=1)

#: A calibrator built rather than fitted, so every weight below is a number the test can state.
#: ``sigmoid(0)`` is exactly 0.5, and the coefficient is what makes a bigger departure weigh more.
FLAT = FittedPlattCalibrator(coefficient=0.0, intercept=0.0)
CERTAIN = FittedPlattCalibrator(coefficient=0.0, intercept=40.0)


def behaviour(
    value: float,
    *,
    index: int = 0,
    feature: str = COMMAND_COUNT,
    device: str = DEVICE,
) -> Observation:
    """Build a command-behaviour observation of the shape `featurise_commands` emits."""
    return Observation(
        entity_ids=[device],
        feature=feature,
        value=value,
        timestamp=EPOCH + WINDOW * index,
        domain=Domain.ATLAS,
        context={
            "device_ip": device.removeprefix("ent_"),
            "window_start": (EPOCH + WINDOW * index).isoformat(),
            "window_end": (EPOCH + WINDOW * (index + 1)).isoformat(),
            "frames": f"{CAPTURE}:{index * 60}-{index * 60 + 59}",
            "frame_count": "60",
            "protocol": "modbus",
        },
    )


def finding(
    feature: str = UNKNOWN_COMMAND_RELATIONSHIP,
    value: float = 5.0,
    *,
    index: int = 0,
    extra: dict[str, str] | None = None,
    issuer: str = DEVICE,
    target: str = TARGET,
) -> Observation:
    """Build a graph finding of the shape `compare_to_graph` emits."""
    context = {
        "issuer_ip": issuer.removeprefix("ent_"),
        "target_ip": target.removeprefix("ent_"),
        "window_start": (EPOCH + WINDOW * index).isoformat(),
        "window_end": (EPOCH + WINDOW * (index + 1)).isoformat(),
        "frames": f"{CAPTURE}:{index * 60}-{index * 60 + 4}",
        "frame_count": "5",
        "protocol": "modbus",
    }
    return Observation(
        entity_ids=[issuer, target],
        feature=feature,
        value=value,
        timestamp=EPOCH + WINDOW * index,
        domain=Domain.ATLAS,
        context={**context, **(extra or {})},
    )


def steady_then_spike() -> tuple[list[Observation], list[Observation]]:
    """Return ``(training, live)`` command counts: 20 steady windows, then a collapse."""
    training = [behaviour(60.0 + (index % 2), index=index) for index in range(20)]
    live = [behaviour(60.0, index=20), behaviour(6.0, index=21)]
    return training, live


def fitted_on_normal() -> GaussianBaseline:
    """Return a baseline fitted on the steady half of `steady_then_spike`."""
    return GaussianBaseline(name="commands")


# ------------------------------------------------------------------------------------------------
# Command behaviour into the existing path
# ------------------------------------------------------------------------------------------------


def test_a_command_departure_becomes_the_same_evidence_a_sensor_departure_does() -> None:
    training, live = steady_then_spike()
    fitted = fitted_on_normal().fit(training)

    departures = promote_command_behaviour(live, fitted, CERTAIN)

    assert len(departures) == 1
    departure = departures[0]
    assert departure.evidence.kind is EvidenceKind.DEVIATION
    assert departure.evidence.domain is Domain.ATLAS
    assert departure.evidence.entity_ids == [DEVICE]
    assert departure.evidence.timestamp == EPOCH + WINDOW * 21
    assert departure.observation.value == 6.0


def test_command_evidence_traces_back_through_the_feature_to_the_frames() -> None:
    """Constitution §3.2, walked end to end: evidence -> deviation -> observation -> frames."""
    training, live = steady_then_spike()
    fitted = fitted_on_normal().fit(training)

    departure = promote_command_behaviour(live, fitted, CERTAIN)[0]

    assert departure.evidence.source_id == departure.deviation.id
    assert departure.deviation.observation_id == departure.observation.id
    assert departure.observation.context["frames"] == f"{CAPTURE}:1260-1319"


def test_the_weight_is_the_calibrated_probability_and_nothing_else() -> None:
    training, live = steady_then_spike()
    fitted = fitted_on_normal().fit(training)

    flat = promote_command_behaviour(live, fitted, FLAT)

    assert flat[0].evidence.weight == pytest.approx(0.5)


def test_a_reading_that_never_left_its_expected_range_produces_no_evidence() -> None:
    """The 4A boundary, exercised through this path rather than assumed to apply to it."""
    training, _ = steady_then_spike()
    fitted = fitted_on_normal().fit(training)

    assert promote_command_behaviour([behaviour(60.0, index=20)], fitted, CERTAIN) == []


def test_a_feature_the_model_never_learned_produces_no_evidence() -> None:
    """Unknown is not anomalous. A feature absent from training has no baseline to depart from."""
    training, _ = steady_then_spike()
    fitted = fitted_on_normal().fit(training)

    novel = behaviour(999.0, index=20, feature="command_count_fn6")

    assert promote_command_behaviour([novel], fitted, CERTAIN) == []


def test_promoting_command_behaviour_refuses_a_graph_finding() -> None:
    """The two streams answer different questions and must not be crossed.

    A graph finding has no learned band and names two entities; scored as behaviour it would be
    attributed to its issuer alone and judged against whatever baseline that key happened to hold.
    """
    training, _ = steady_then_spike()
    fitted = fitted_on_normal().fit(training)

    with pytest.raises(ValueError, match="relationship"):
        promote_command_behaviour([finding()], fitted, CERTAIN)


def test_command_departures_come_back_in_a_deterministic_order() -> None:
    training, _ = steady_then_spike()
    fitted = fitted_on_normal().fit(training)
    live = [behaviour(6.0, index=21), behaviour(5.0, index=20)]

    ordered = promote_command_behaviour(live, fitted, CERTAIN)
    reversed_input = promote_command_behaviour(list(reversed(live)), fitted, CERTAIN)

    stamps = [departure.observation.timestamp for departure in ordered]
    assert stamps == sorted(stamps)
    assert stamps == [departure.observation.timestamp for departure in reversed_input]


# ------------------------------------------------------------------------------------------------
# Graph changes as evidence
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("feature", "extra"),
    [
        (UNKNOWN_COMMAND_RELATIONSHIP, {"function_codes": "6"}),
        (SILENT_COMMAND_RELATIONSHIP, {"learned_command_count": "121"}),
        (UNEXPECTED_COMMAND_FUNCTION, {"function_code": "6", "function_name": "write_register"}),
    ],
)
def test_each_graph_change_becomes_traceable_relationship_evidence(
    feature: str, extra: dict[str, str]
) -> None:
    changes = promote_graph_findings([finding(feature, extra=extra)], CERTAIN)

    assert len(changes) == 1
    change = changes[0]
    assert change.evidence.kind is EvidenceKind.RELATIONSHIP_CHANGE
    assert change.evidence.entity_ids == [DEVICE, TARGET]
    assert change.evidence.source_id == change.finding.id
    assert change.finding.context["frames"].startswith(CAPTURE)


def test_a_silence_summary_records_learned_vs_live_span() -> None:
    """Duration mismatch must be readable from the evidence sentence, not only from context."""
    change = promote_graph_findings(
        [
            finding(
                SILENT_COMMAND_RELATIONSHIP,
                60.5,
                extra={
                    "learned_command_count": "121",
                    "learned_span_seconds": "432000",
                    "live_span_seconds": "86400",
                },
            )
        ],
        CERTAIN,
    )[0]

    assert "comparable stretch" in change.evidence.summary
    assert "learned 432000s vs live 86400s" in change.evidence.summary
    """An operator reads the summary, so it must say what happened without a second lookup."""
    change = promote_graph_findings(
        [finding(UNKNOWN_COMMAND_RELATIONSHIP, 5.0, extra={"function_codes": "6"})], CERTAIN
    )[0]

    assert "10.0.0.9" in change.evidence.summary
    assert "10.0.0.20" in change.evidence.summary
    assert "5" in change.evidence.summary
    assert change.evidence.summary.startswith(graph_finding_marker(UNKNOWN_COMMAND_RELATIONSHIP))
    assert graph_finding_feature_of(change.evidence) == UNKNOWN_COMMAND_RELATIONSHIP


def test_an_unmarked_summary_declares_no_graph_finding() -> None:
    """A fixture that never stamped the marker must not be read as an unknown master."""
    unmarked = Evidence(
        kind=EvidenceKind.RELATIONSHIP_CHANGE,
        source_id="obs_00000000000f",
        entity_ids=[DEVICE, TARGET],
        timestamp=EPOCH,
        domain=Domain.ATLAS,
        weight=0.8,
        summary="a command relationship changed",
    )
    assert graph_finding_feature_of(unmarked) is None
    assert GRAPH_FINDING_MARKER not in unmarked.summary


def test_promoting_graph_findings_refuses_a_feature_it_cannot_read() -> None:
    """Summarising an unrecognised feature would describe a change nothing measured."""
    with pytest.raises(ValueError, match="not a command-graph finding"):
        promote_graph_findings([behaviour(5.0)], CERTAIN)


def test_graph_changes_come_back_in_a_deterministic_order() -> None:
    findings = [
        finding(UNEXPECTED_COMMAND_FUNCTION, index=2, extra={"function_code": "6"}),
        finding(UNKNOWN_COMMAND_RELATIONSHIP, index=1, extra={"function_codes": "6"}),
    ]

    changes = promote_graph_findings(findings, CERTAIN)

    stamps = [change.finding.timestamp for change in changes]
    assert stamps == sorted(stamps)


# ------------------------------------------------------------------------------------------------
# The two streams together
# ------------------------------------------------------------------------------------------------


def test_command_evidence_merges_both_streams_in_time_order() -> None:
    training, live = steady_then_spike()
    fitted = fitted_on_normal().fit(training)
    bundle = CommandEvidence(
        departures=tuple(promote_command_behaviour(live, fitted, CERTAIN)),
        changes=tuple(
            promote_graph_findings(
                [finding(UNKNOWN_COMMAND_RELATIONSHIP, index=25, extra={"function_codes": "6"})],
                CERTAIN,
            )
        ),
    )

    stamps = [item.timestamp for item in bundle.evidence()]
    assert len(stamps) == 2
    assert stamps == sorted(stamps)


def test_an_empty_bundle_is_empty_rather_than_an_error() -> None:
    assert CommandEvidence().evidence() == ()


def test_the_caveats_say_the_detection_result_is_unmeasured() -> None:
    """P3's central honesty guard, pinned so it cannot be dropped by a later edit."""
    assert UNMEASURED_COMMAND_DETECTION_CAVEAT in COMMAND_EVIDENCE_CAVEATS
    assert "HAS NOT BEEN MEASURED" in UNMEASURED_COMMAND_DETECTION_CAVEAT


def test_the_ungrouped_caveat_names_reachability_and_refuses_co_movement() -> None:
    """ADR 0014 Decision 2's 'nothing declared to group by' is superseded; co-movement is not."""
    assert UNGROUPED_COMMAND_EVIDENCE_CAVEAT in COMMAND_EVIDENCE_CAVEATS
    assert "reachability" in UNGROUPED_COMMAND_EVIDENCE_CAVEAT.lower()
    assert "co-movement" in UNGROUPED_COMMAND_EVIDENCE_CAVEAT
    assert "not collapsed" in UNGROUPED_COMMAND_EVIDENCE_CAVEAT.lower() or "NOT collapsed" in (
        UNGROUPED_COMMAND_EVIDENCE_CAVEAT
    )


# ------------------------------------------------------------------------------------------------
# The discrimination: what commands let the reasoning engine say that telemetry could not
# ------------------------------------------------------------------------------------------------


def confidences(*evidence_streams: Sequence[Evidence]) -> dict[str, float]:
    """Ingest evidence into a fresh Atlas reasoning engine and return the competing confidences."""
    engine = ReasoningEngine(
        atlas_library(),
        InMemoryEvidenceStore(),
        ReasoningConfig(correlation_window=timedelta(hours=1)),
    )
    for stream in evidence_streams:
        engine.ingest(stream)
    return {
        hypothesis.template_id: hypothesis.confidence
        for hypothesis in engine.competing(Domain.ATLAS)
    }


def subsystem_event(weight: float = 1.0) -> Evidence:
    """Build the grouped sensor evidence 5C produces: a broad departure on one unit."""
    return Evidence(
        kind=EvidenceKind.DEVIATION,
        source_id="subsystem-event:ev_000000000001,ev_000000000002,ev_000000000003",
        entity_ids=["P1_FT01", "P1_LIT01", "P1_PIT01"],
        timestamp=EPOCH,
        domain=Domain.ATLAS,
        weight=weight,
        summary="P1: 3 signals departed together",
    )


def test_sensor_evidence_alone_leaves_the_benign_explanation_ahead() -> None:
    """The starting position, and the reason the packet adapter was built.

    A broad departure supports both explanations identically, so their odds ratio never moves off
    the ratio of their priors — one rank, or a factor of three.
    """
    table = confidences([subsystem_event()])

    assert table[PROCESS_DISTURBANCE_TEMPLATE_ID] > table[UNAUTHORISED_CONTROL_TEMPLATE_ID]


def test_one_command_graph_finding_reverses_that_ordering() -> None:
    """The discrimination, with the arithmetic stated rather than merely observed.

    Priors sit one rank apart, so the upset starts with three times the odds. A structural change
    of weight ``w`` supports the malicious explanation and contradicts the upset, moving the odds
    ratio by ``exp(2 * EVIDENCE_STRENGTH * w)``. At ``w = 1`` that is a factor of nine against a
    head start of three, so the ordering flips — and this is the smallest evidence that could do it.
    """
    change = promote_graph_findings(
        [finding(UNKNOWN_COMMAND_RELATIONSHIP, 5.0, extra={"function_codes": "6"})], CERTAIN
    )
    assert change[0].evidence.weight == pytest.approx(1.0)

    table = confidences([subsystem_event()], [change[0].evidence])

    assert table[UNAUTHORISED_CONTROL_TEMPLATE_ID] > table[PROCESS_DISTURBANCE_TEMPLATE_ID]

    swing = math.exp(2.0 * EVIDENCE_STRENGTH * change[0].evidence.weight)
    assert swing > 3.0


def test_an_unknown_master_outranks_maintenance_after_a_broad_process_event() -> None:
    """The ranking the cycle contract measures: unknown-master writes make the attack lead.

    Maintenance starts one rank ahead. A fully-trusted unknown-master finding *contradicts*
    maintenance (odds / 3) and *supports* the attack (odds x 3), while a broad subsystem event
    supports only the attack. After both, the attack's odds sit well above maintenance's — the
    tie that used to break alphabetically onto ``engineering_maintenance`` is gone.
    """
    change = promote_graph_findings(
        [finding(UNKNOWN_COMMAND_RELATIONSHIP, 5.0, extra={"function_codes": "6"})], CERTAIN
    )
    table = confidences([subsystem_event(weight=1.0)], [change[0].evidence])

    assert table[UNAUTHORISED_CONTROL_TEMPLATE_ID] > table[ENGINEERING_MAINTENANCE_TEMPLATE_ID]
    assert table[UNAUTHORISED_CONTROL_TEMPLATE_ID] > table[PROCESS_DISTURBANCE_TEMPLATE_ID]


def test_the_reversal_needs_evidence_the_calibrator_actually_believes() -> None:
    """A half-trusted structural change moves the odds by exactly three — a tie, not a reversal.

    The boundary case is worth pinning: it shows the flip is produced by the calibrated weight
    rather than by the mere presence of a relationship change.
    """
    change = promote_graph_findings(
        [finding(UNKNOWN_COMMAND_RELATIONSHIP, 5.0, extra={"function_codes": "6"})], FLAT
    )
    assert change[0].evidence.weight == pytest.approx(0.5)

    table = confidences([subsystem_event()], [change[0].evidence])

    assert table[UNAUTHORISED_CONTROL_TEMPLATE_ID] == pytest.approx(
        table[PROCESS_DISTURBANCE_TEMPLATE_ID], rel=1e-9
    )


def test_a_command_graph_finding_lands_in_the_narrative_it_explains() -> None:
    """Integration, not just matching: the evidence must be reachable from the story it moved."""
    engine = ReasoningEngine(
        atlas_library(),
        InMemoryEvidenceStore(),
        ReasoningConfig(correlation_window=timedelta(hours=1)),
    )
    change = promote_graph_findings(
        [finding(UNKNOWN_COMMAND_RELATIONSHIP, 5.0, extra={"function_codes": "6"})], CERTAIN
    )[0]
    engine.ingest([subsystem_event(), change.evidence])

    narratives = engine.narratives()

    assert len(narratives) == 1
    assert change.evidence.id in narratives[0].evidence_ids

    by_id = {hypothesis.id: hypothesis for hypothesis in engine.hypotheses()}
    ranked = [by_id[hypothesis_id].template_id for hypothesis_id in narratives[0].hypothesis_ids]
    # "We do not yet know" still leads on one piece of evidence, and should: a prior of 0.30 is not
    # displaced by a single observation, which is the modesty phos.reasoning.belief was built for.
    assert ranked[0] == INSUFFICIENT_EVIDENCE_TEMPLATE_ID
    assert ranked.index(UNAUTHORISED_CONTROL_TEMPLATE_ID) < ranked.index(
        PROCESS_DISTURBANCE_TEMPLATE_ID
    )
    malicious = next(
        hypothesis
        for hypothesis in engine.hypotheses()
        if hypothesis.template_id == UNAUTHORISED_CONTROL_TEMPLATE_ID
    )
    assert change.evidence.id in malicious.supporting


def test_a_command_behaviour_departure_carries_the_two_control_explanations() -> None:
    """It bears on the two explanations that involve operating a device, and joins the story.

    Before ADR 0071 this fact reached no hypothesis at all and the assertion here was that it
    supported nothing. What has not changed is the second half: it is evidence an operator must be
    shown, so it is still in the narrative whether or not any template weighs it.
    """
    training, live = steady_then_spike()
    fitted = fitted_on_normal().fit(training)
    departure = promote_command_behaviour(live, fitted, CERTAIN)[0]

    engine = ReasoningEngine(
        atlas_library(),
        InMemoryEvidenceStore(),
        ReasoningConfig(correlation_window=timedelta(hours=2)),
    )
    engine.ingest([departure.evidence])

    carried = {
        hypothesis.template_id
        for hypothesis in engine.hypotheses()
        if departure.evidence.id in {*hypothesis.supporting, *hypothesis.contradictory}
    }

    assert carried == {ENGINEERING_MAINTENANCE_TEMPLATE_ID, UNAUTHORISED_CONTROL_TEMPLATE_ID}
    assert all(
        departure.evidence.id not in hypothesis.contradictory for hypothesis in engine.hypotheses()
    )
    assert engine.narratives()[0].evidence_ids == [departure.evidence.id]


def test_evidence_roles_are_reconstructable_from_what_was_stored() -> None:
    """Constitution §3.2 for the command path: the role each fact played is on the hypothesis."""
    change = promote_graph_findings(
        [finding(UNKNOWN_COMMAND_RELATIONSHIP, 5.0, extra={"function_codes": "6"})], CERTAIN
    )[0]
    engine = ReasoningEngine(atlas_library(), InMemoryEvidenceStore())
    engine.ingest([change.evidence])

    roles = {
        hypothesis.template_id: (
            EvidenceRole.SUPPORTING
            if change.evidence.id in hypothesis.supporting
            else EvidenceRole.CONTRADICTORY
        )
        for hypothesis in engine.hypotheses()
        if change.evidence.id in {*hypothesis.supporting, *hypothesis.contradictory}
    }

    assert roles[UNAUTHORISED_CONTROL_TEMPLATE_ID] is EvidenceRole.SUPPORTING
    assert roles[PROCESS_DISTURBANCE_TEMPLATE_ID] is EvidenceRole.CONTRADICTORY


def test_a_deviation_about_an_observation_that_was_not_scored_is_refused() -> None:
    """A detection that cannot be traced back to a measurement is not a detection (§3.2).

    `phos.models.ModelDetector` and `CalibratedModelDetector` both refuse this; the command path
    refuses it too rather than trusting that every model it is handed keeps the invariant.
    """
    from phos.models import FittedModel
    from phos.ontology import Deviation, ExpectedRange

    class Fabricating(FittedModel):
        """A model that scores an observation nobody gave it."""

        def score(self, observations: Sequence[Observation]) -> list[Deviation]:
            """Return one deviation naming an observation id that is not in ``observations``."""
            return [
                Deviation(
                    observation_id="obs_thatnobodygave",
                    expected=ExpectedRange(
                        feature=COMMAND_COUNT,
                        entity_id=DEVICE,
                        low=0.0,
                        high=1.0,
                        mean=0.5,
                        stddev=0.1,
                        learned_from_window=(EPOCH, EPOCH),
                    ),
                    magnitude=9.0,
                    timestamp=EPOCH,
                )
            ]

    fabricating = Fabricating(name="fabricating", expected_ranges={}, feature_ranges={}, emit_k=1.0)

    with pytest.raises(ValueError, match="unknown observation"):
        promote_command_behaviour([behaviour(60.0)], fabricating, CERTAIN)


def test_a_silent_unrelated_poller_does_not_support_maintenance_for_a_rogue_write() -> None:
    """A silent learned link with no path to the window's issuer is not maintenance evidence.

    This is session 3's primary success. The silence finding is still stored as evidence so an
    operator can see it as its own story; it must not accumulate on engineering_maintenance
    beside the rogue write.
    """
    rogue = promote_graph_findings(
        [finding(UNKNOWN_COMMAND_RELATIONSHIP, extra={"function_codes": "6"})], CERTAIN
    )[0]
    silence = promote_graph_findings(
        [
            finding(
                SILENT_COMMAND_RELATIONSHIP,
                extra={"learned_command_count": "121"},
                issuer=POLLER,
                target=OTHER_PLC,
            )
        ],
        CERTAIN,
    )[0]

    engine = ReasoningEngine(
        atlas_library(),
        InMemoryEvidenceStore(),
        ReasoningConfig(correlation_window=timedelta(hours=1)),
    )
    engine.ingest([subsystem_event(), rogue.evidence, silence.evidence])

    maintenance = next(
        hypothesis
        for hypothesis in engine.hypotheses()
        if hypothesis.template_id == ENGINEERING_MAINTENANCE_TEMPLATE_ID
    )
    attack = next(
        hypothesis
        for hypothesis in engine.hypotheses()
        if hypothesis.template_id == UNAUTHORISED_CONTROL_TEMPLATE_ID
    )
    cited_maintenance = {*maintenance.supporting, *maintenance.contradictory}
    cited_attack = {*attack.supporting, *attack.contradictory}

    assert silence.evidence.id not in cited_maintenance
    assert silence.evidence.id not in cited_attack
    assert rogue.evidence.id in maintenance.contradictory
    assert rogue.evidence.id in attack.supporting

    stories = engine.narratives()
    maintenance_edges = [
        (source, target)
        for story in stories
        for source, target in story.causal_edges
        if target == maintenance.id
    ]
    assert silence.evidence.id not in {source for source, _ in maintenance_edges}


def test_silence_that_shares_an_entity_with_an_unexpected_function_still_supports_maintenance() -> (
    None
):
    """Chatty learned links remain attachable when they share an entity with the command act."""
    write = promote_graph_findings(
        [finding(UNEXPECTED_COMMAND_FUNCTION, extra={"function_code": "6"})], CERTAIN
    )[0]
    silence = promote_graph_findings(
        [finding(SILENT_COMMAND_RELATIONSHIP, extra={"learned_command_count": "121"})], CERTAIN
    )[0]

    engine = ReasoningEngine(
        atlas_library(),
        InMemoryEvidenceStore(),
        ReasoningConfig(correlation_window=timedelta(hours=1)),
    )
    engine.ingest([write.evidence, silence.evidence])

    maintenance = next(
        hypothesis
        for hypothesis in engine.hypotheses()
        if hypothesis.template_id == ENGINEERING_MAINTENANCE_TEMPLATE_ID
    )
    assert write.evidence.id in maintenance.supporting
    assert silence.evidence.id in maintenance.supporting
