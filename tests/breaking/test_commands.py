"""Ranking competing explanations, and reading only the ordering rather than the confidence."""

from datetime import UTC, datetime, timedelta

from tests.breaking.conftest import RUN_START, ground_truth

from phos.atlas.packet import CommandEdge, DeviceCommandGraph, device_entity_id
from phos.breaking.commands import (
    ATTACK_TEMPLATE_ID,
    CommandIssuerKind,
    CommandReasoningResult,
    ExplanationRanking,
    classify_command_issuer,
    command_attacks,
    rank_explanations,
)
from phos.eval import Dataset
from phos.ontology import (
    Domain,
    Evidence,
    EvidenceKind,
    Hypothesis,
    HypothesisStatus,
    InMemoryEvidenceStore,
    Observation,
)
from phos.reasoning.belief import LEAD_TIE_EPSILON
from phos.synth.attacks import AttackType
from phos.synth.plants.water import WATER_DESCRIPTION

ENTITY = "ent_test0000000001"


def store_with(
    *,
    in_window: dict[str, float],
    out_of_window: dict[str, float] | None = None,
) -> InMemoryEvidenceStore:
    """Build a store where each named template has a hypothesis at the given confidence.

    ``in_window`` hypotheses are supported by evidence stamped inside the fixture attack's window;
    ``out_of_window`` ones by evidence an hour after it closes, so they must not be ranked.
    """
    store = InMemoryEvidenceStore()

    def add(template: str, confidence: float, at: object) -> None:
        observation = Observation(
            timestamp=at,  # type: ignore[arg-type]
            feature="level_m",
            value=1.0,
            domain=Domain.ATLAS,
            entity_ids=[ENTITY],
        )
        store.add_observation(observation)
        evidence = Evidence(
            kind=EvidenceKind.DEVIATION,
            domain=Domain.ATLAS,
            timestamp=at,  # type: ignore[arg-type]
            summary=f"{template} evidence",
            weight=0.5,
            entity_ids=[ENTITY],
            source_id=observation.id,
        )
        store.add_evidence(evidence)
        store.add_hypothesis(
            Hypothesis(
                label=template.replace("_", " "),
                template_id=template,
                domain=Domain.ATLAS,
                prior=0.1,
                confidence=confidence,
                status=HypothesisStatus.ACTIVE,
                supporting=[evidence.id],
            )
        )

    inside = RUN_START + timedelta(hours=2)
    outside = RUN_START + timedelta(hours=6)
    for template, confidence in in_window.items():
        add(template, confidence, inside)
    for template, confidence in (out_of_window or {}).items():
        add(template, confidence, outside)
    return store


def corpus_dataset() -> Dataset:
    """A named corpus, for the log line the ranker writes."""
    return Dataset(name="fixture", domain=Domain.ATLAS, observations=[])


def test_explanations_are_ranked_strongest_first() -> None:
    truth = ground_truth("a", AttackType.ROGUE_COMMAND, targets=("level_setpoint_m",), issuer="d1")
    store = store_with(
        in_window={
            "process_disturbance": 0.4,
            ATTACK_TEMPLATE_ID: 0.6,
            "sensor_or_device_fault": 0.2,
        }
    )
    ranking = rank_explanations(truth, store, corpus_dataset())
    assert ranking.templates[0] == ATTACK_TEMPLATE_ID
    assert ranking.rank == 1
    assert ranking.leads
    assert ranking.n_hypotheses == 3


def test_a_hypothesis_supported_only_outside_the_window_is_not_ranked() -> None:
    """An explanation of another moment is not an explanation of this attack."""
    truth = ground_truth("a", AttackType.ROGUE_COMMAND, targets=("level_setpoint_m",), issuer="d1")
    store = store_with(
        in_window={"process_disturbance": 0.4},
        out_of_window={ATTACK_TEMPLATE_ID: 0.9},
    )
    ranking = rank_explanations(truth, store, corpus_dataset())
    assert ranking.rank is None
    assert ranking.confidence == 0.0
    assert ranking.n_hypotheses == 1


def test_the_attack_explanation_can_be_present_without_leading() -> None:
    truth = ground_truth("a", AttackType.ROGUE_COMMAND, targets=("level_setpoint_m",), issuer="d1")
    store = store_with(
        in_window={
            "sensor_or_device_fault": 0.8,
            "process_disturbance": 0.5,
            ATTACK_TEMPLATE_ID: 0.3,
        }
    )
    ranking = rank_explanations(truth, store, corpus_dataset())
    assert ranking.rank == 3
    assert not ranking.leads


def test_an_empty_store_ranks_nothing() -> None:
    truth = ground_truth("a", AttackType.ROGUE_COMMAND, targets=("level_setpoint_m",), issuer="d1")
    ranking = rank_explanations(truth, InMemoryEvidenceStore(), corpus_dataset())
    assert ranking.templates == ()
    assert ranking.rank is None
    assert ranking.tied_leaders == ()
    assert ranking.unique_leader is None


def test_a_ceiling_tie_is_not_a_unique_leader() -> None:
    """Saturated attack vs maintenance is a refusal, not an alphabetical win.

    Constitution §3.7 requires a reproducible order of the tied ids. It does not license naming
    `engineering_maintenance` the unique leader because it sorts first. `leads` stays false.
    """
    truth = ground_truth("a", AttackType.ROGUE_COMMAND, targets=("level_setpoint_m",), issuer="d1")
    store = store_with(
        in_window={
            "engineering_maintenance": 1.0,
            ATTACK_TEMPLATE_ID: 1.0,
            "process_disturbance": 0.4,
        }
    )
    ranking = rank_explanations(truth, store, corpus_dataset())

    assert ranking.tied_leaders == ("engineering_maintenance", ATTACK_TEMPLATE_ID)
    assert ranking.unique_leader is None
    assert not ranking.leads
    assert ranking.rank != 1
    assert ranking.templates[0] == "engineering_maintenance"
    assert ranking.templates.index("engineering_maintenance") < ranking.templates.index(
        ATTACK_TEMPLATE_ID
    )


def test_an_epsilon_tie_away_from_the_ceiling_is_also_a_refusal() -> None:
    """A declared epsilon, not a battery-fitted band: equal mid-range confidences are a tie."""
    truth = ground_truth("a", AttackType.ROGUE_COMMAND, targets=("level_setpoint_m",), issuer="d1")
    store = store_with(
        in_window={
            "engineering_maintenance": 0.55,
            ATTACK_TEMPLATE_ID: 0.55 + LEAD_TIE_EPSILON / 2,
        }
    )
    ranking = rank_explanations(truth, store, corpus_dataset())

    assert ranking.tied_leaders == ("engineering_maintenance", ATTACK_TEMPLATE_ID)
    assert not ranking.leads
    assert ranking.unique_leader is None


def test_a_separated_runner_up_is_not_tied() -> None:
    """Epsilon is not a knob that blankets every close race. A clear gap is a unique lead."""
    truth = ground_truth("a", AttackType.ROGUE_COMMAND, targets=("level_setpoint_m",), issuer="d1")
    store = store_with(
        in_window={
            ATTACK_TEMPLATE_ID: 0.80,
            "engineering_maintenance": 0.80 - 1e-6,
        }
    )
    ranking = rank_explanations(truth, store, corpus_dataset())

    assert ranking.tied_leaders == ()
    assert ranking.unique_leader == ATTACK_TEMPLATE_ID
    assert ranking.leads
    assert ranking.rank == 1


def test_the_same_tie_lists_the_same_ids_on_every_call() -> None:
    """Determinism: two runs over one store agree on the tied set and on list order."""
    truth = ground_truth("a", AttackType.ROGUE_COMMAND, targets=("level_setpoint_m",), issuer="d1")
    store = store_with(
        in_window={
            ATTACK_TEMPLATE_ID: 1.0,
            "engineering_maintenance": 1.0,
            "sensor_or_device_fault": 1.0,
        }
    )
    first = rank_explanations(truth, store, corpus_dataset())
    second = rank_explanations(truth, store, corpus_dataset())

    assert first.tied_leaders == second.tied_leaders
    assert first.templates == second.templates
    assert first.tied_leaders == (
        "engineering_maintenance",
        "sensor_or_device_fault",
        ATTACK_TEMPLATE_ID,
    )


# --- what counts as movement ---------------------------------------------


def result(before: int | None, after: int | None, *, evidence: int = 5) -> CommandReasoningResult:
    """A comparison with the two ranks held fixed."""
    return CommandReasoningResult(
        attack_id="a",
        subtlety=0.5,
        sensor_only=ExplanationRanking(attack_id="a", rank=before, n_hypotheses=3),
        with_commands=ExplanationRanking(attack_id="a", rank=after, n_hypotheses=4),
        n_command_evidence=evidence,
    )


def test_appearing_at_all_counts_as_movement() -> None:
    """The measured case: not raised on sensors, raised once the commands were readable."""
    assert result(None, 2).moved_toward_attack


def test_climbing_counts_as_movement() -> None:
    assert result(3, 1).moved_toward_attack


def test_standing_still_is_not_movement() -> None:
    assert not result(2, 2).moved_toward_attack


def test_falling_is_not_movement() -> None:
    assert not result(1, 3).moved_toward_attack


def test_disappearing_is_not_movement() -> None:
    assert not result(2, None).moved_toward_attack


def test_confidence_alone_never_counts_as_movement() -> None:
    """The confidences are uncalibrated, so only the ordering may be read (Constitution §3.3)."""
    quiet = CommandReasoningResult(
        attack_id="a",
        subtlety=0.5,
        sensor_only=ExplanationRanking(attack_id="a", rank=2, confidence=0.10),
        with_commands=ExplanationRanking(attack_id="a", rank=2, confidence=0.95),
    )
    assert not quiet.moved_toward_attack


def test_newly_leading_requires_it_not_to_have_led_before() -> None:
    assert result(2, 1).newly_leads
    assert not result(1, 1).newly_leads


def test_a_ceiling_tie_never_counts_as_newly_leading() -> None:
    """Session 1 success is not the attack explanation newly_leads."""
    comparison = CommandReasoningResult(
        attack_id="a",
        subtlety=0.5,
        sensor_only=ExplanationRanking(
            attack_id="a",
            templates=("process_disturbance", "sensor_or_device_fault", ATTACK_TEMPLATE_ID),
            rank=3,
            n_hypotheses=3,
        ),
        with_commands=ExplanationRanking(
            attack_id="a",
            templates=("engineering_maintenance", ATTACK_TEMPLATE_ID),
            rank=2,
            confidence=1.0,
            n_hypotheses=2,
            tied_leaders=("engineering_maintenance", ATTACK_TEMPLATE_ID),
        ),
        n_command_evidence=5,
    )
    assert comparison.moved_toward_attack
    assert not comparison.with_commands.leads
    assert not comparison.newly_leads


def test_two_tied_unauthorised_hypotheses_at_rank_one_do_not_uniquely_lead() -> None:
    """The unknown-master subtle shape: rank 1 with non-empty tied_leaders is not a unique lead.

    Two ``unauthorised_control_activity`` hypotheses can share the ceiling. ``tied_leaders`` then
    holds that one template id. Counting ``rank == 1`` as ``leads`` would invent a winner ADR 0036
    refused.
    """
    ranking = ExplanationRanking(
        attack_id="wt-unknown-master-subtle",
        templates=(ATTACK_TEMPLATE_ID, ATTACK_TEMPLATE_ID),
        rank=1,
        confidence=1.0,
        n_hypotheses=2,
        tied_leaders=(ATTACK_TEMPLATE_ID,),
    )
    assert ranking.unique_leader is None
    assert not ranking.leads
    comparison = CommandReasoningResult(
        attack_id="wt-unknown-master-subtle",
        subtlety=0.7,
        sensor_only=ExplanationRanking(
            attack_id="wt-unknown-master-subtle",
            templates=("sensor_or_device_fault", ATTACK_TEMPLATE_ID),
            rank=2,
            n_hypotheses=2,
        ),
        with_commands=ranking,
        n_command_evidence=8,
    )
    assert comparison.moved_toward_attack
    assert not comparison.newly_leads


def test_insufficient_evidence_listed_first_is_not_command_reasoning_lead() -> None:
    """The residual at the front is a refusal, not an unauthorised unique lead."""
    ranking = ExplanationRanking(
        attack_id="a",
        templates=("insufficient_evidence", ATTACK_TEMPLATE_ID),
        rank=2,
        n_hypotheses=2,
    )
    assert ranking.unique_leader == "insufficient_evidence"
    assert not ranking.leads
    comparison = CommandReasoningResult(
        attack_id="a",
        subtlety=0.5,
        sensor_only=ExplanationRanking(attack_id="a", rank=3, n_hypotheses=3),
        with_commands=ranking,
        n_command_evidence=5,
    )
    assert not comparison.newly_leads


# --- which attacks the command path applies to ---------------------------


def test_only_control_network_attacks_are_measured_for_commands() -> None:
    """An actuator manipulation puts nothing on the wire, so it is evidence about neither side."""
    truths = (
        ground_truth("cmd", AttackType.ROGUE_COMMAND, targets=("level_setpoint_m",), issuer="d1"),
        ground_truth("mimic", AttackType.MIMIC_COMMAND, targets=("level_setpoint_m",), issuer="d1"),
        ground_truth("blatant", AttackType.BLATANT, targets=("pump_pct",)),
        ground_truth("liar", AttackType.LIAR, targets=("level_m",)),
    )
    assert [t.attack_id for t in command_attacks(truths)] == ["cmd", "mimic"]


def test_the_target_explanation_is_named_rather_than_inferred() -> None:
    """The measurement asks whether Atlas reaches THIS conclusion, not whichever one won."""
    assert ATTACK_TEMPLATE_ID == "unauthorised_control_activity"


def _graph_with_scada_issuer() -> DeviceCommandGraph:
    """A baseline graph on which the water SCADA poller already commands a PLC."""
    network = WATER_DESCRIPTION.control_network
    assert network is not None
    scada_ip = network.node("scada").ip
    plc_ip = network.node("plc_outlet").ip
    instant = datetime(2026, 5, 1, tzinfo=UTC)
    edge = CommandEdge(
        issuer=device_entity_id(scada_ip),
        target=device_entity_id(plc_ip),
        issuer_ip=scada_ip,
        target_ip=plc_ip,
        function_codes=(3,),
        command_count=10,
        first_seen=instant,
        last_seen=instant,
        frames="baseline:0-1",
    )
    return DeviceCommandGraph(edges=(edge,), learned_span=(instant, instant))


def test_a_polling_scada_write_is_a_known_station() -> None:
    """The graded battery's rogue issuer: on the graph, so ADR 0027 does not apply."""
    kind = classify_command_issuer("scada", WATER_DESCRIPTION, _graph_with_scada_issuer())
    assert kind is CommandIssuerKind.KNOWN_STATION


def test_a_silent_engineering_write_is_an_unknown_master() -> None:
    kind = classify_command_issuer("engineering", WATER_DESCRIPTION, _graph_with_scada_issuer())
    assert kind is CommandIssuerKind.UNKNOWN_MASTER
