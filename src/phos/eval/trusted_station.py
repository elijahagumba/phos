"""Trusted-station command effects on the water plant (ADR 0250).

Each seed is two in-memory runs. Both issuers are the plant's declared operator. One write
moves the clearwell setpoint toward the low safety limit while the level is already short,
which is against the call to raise it. The other raises the setpoint, with that call. Neither
run is an unknown master. Nothing is written under ``data/``.

A unique lead is `unauthorised_control_activity` at the front of `competing`, with
`tied_lead_ids` empty. `insufficient_evidence` listed first is not a lead (ADR 0036).

False alarms follow ADR 0086 as lane T states it. Silence is 0. A narrative that does not
concern the authorised write counts. Maintenance that is about that write does not. Any other
narrative counts. The bar is not above 0.20.

Held-back seeds are refused until a declaration is in HEAD and the output file is absent.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

from phos.atlas.command_effect import (
    TOWARD_LIMIT_AGAINST_STATE,
    WRITE_AND_HIDE,
    OperatorWrite,
    command_effect_evidence,
)
from phos.atlas.command_response import CommandResponsePair, declared_pairs
from phos.atlas.templates import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
    atlas_library,
)
from phos.eval.build_declaration import TRUSTED_DEVELOPMENT_SEEDS, TRUSTED_HELD_BACK_SEEDS
from phos.ontology import Domain, Entity, EntityType, Evidence, InMemoryEvidenceStore
from phos.reasoning import (
    INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    FittedPlattCalibrator,
    ReasoningConfig,
    ReasoningEngine,
    tied_lead_ids,
)
from phos.synth.command import NoCommands, PlannedCommandSource, PlannedWrite
from phos.synth.injection import CompositeInjection, HoldActuator, HoldReading, TimeWindow
from phos.synth.plant import PlantDescription, RunSpec
from phos.synth.plants.water import (
    BACKWASH,
    CLEARWELL_LEVEL,
    ENGINEERING,
    INTAKE_SPEED,
    INTAKE_STOP,
    LEVEL_SETPOINT,
    LEVEL_SETPOINT_OPERATING_HIGH,
    LEVEL_SETPOINT_OPERATING_LOW,
    WATER_DESCRIPTION,
)
from phos.synth.run import PlantRun, run_plant

__all__ = [
    "AUTHORISED_SETPOINT",
    "CHALLENGER_FEATURES",
    "CHALLENGER_FILES",
    "HOSTILE_SETPOINT",
    "PLANT_ID",
    "RESULT_NAME",
    "WRITE_AT",
    "CaseScore",
    "SeedScore",
    "challenger_sha256",
    "false_alarm_count",
    "held_back_allowed",
    "render_held_back",
    "run_case",
    "run_quiet",
    "score_case",
    "score_development",
    "score_held_back",
    "score_seed",
]

logger = logging.getLogger(__name__)

PLANT_ID: Final = "water-treatment"
RESULT_NAME: Final = "trusted-station:known-operator-effect"
WRITE_AT: Final = 12
"""Sample of the single operator write. The plant's first benign event is not before sample 30."""

HOSTILE_SETPOINT: Final = 0.4
"""Toward the clearwell's low safety limit, against a level that is already short."""

AUTHORISED_SETPOINT: Final = 4.5
"""A jump upward, with the call to raise a short clearwell. Unusual, and not toward empty."""

_N_STEPS: Final = 40
_SAMPLE: Final = timedelta(seconds=120)
_HOLD_INTAKE: Final = 10.0
_START: Final = datetime(2026, 10, 1, tzinfo=UTC)
_WEIGHT: Final = FittedPlattCalibrator(coefficient=0.0, intercept=0.0)
_INTAKE: Final = INTAKE_SPEED
_MANUAL_MODES: Final = frozenset({BACKWASH, INTAKE_STOP})
_H1: Final = frozenset({TOWARD_LIMIT_AGAINST_STATE})
CHALLENGER_FEATURES: Final = frozenset({TOWARD_LIMIT_AGAINST_STATE, WRITE_AND_HIDE})
"""H1 and H3. H2 is rejected (ADR 0252) and is not in this set."""

CHALLENGER_FILES: Final = (
    "src/phos/ontology/enums.py",
    "src/phos/atlas/command_effect.py",
    "src/phos/atlas/templates.py",
    "src/phos/eval/trusted_station.py",
)
"""The files whose bytes are the frozen challenger. The declaration ADR is not one of them."""


@dataclass(frozen=True)
class CaseScore:
    """One run: whether unauthorised uniquely led, and how many false-alarm narratives it raised.

    Attributes:
        kind: ``hostile`` or ``authorised``.
        issuer: The node that wrote. Lane T requires the declared operator.
        n_facts: Command-effect facts promoted.
        lead: The narrative lead, or empty when the run stayed silent.
        tied: Template ids sharing the lead. Empty when the lead is unique or the run is silent.
        uniquely_leads: Unauthorised control is the unique narrative lead.
        false_alarms: Narratives counted against an authorised run. Zero on a hostile run.
        concerns_write: Whether the facts name the written setpoint.
    """

    kind: str
    issuer: str
    n_facts: int
    lead: str
    tied: tuple[str, ...]
    uniquely_leads: bool
    false_alarms: int
    concerns_write: bool


@dataclass(frozen=True)
class SeedScore:
    """Both runs of one seed."""

    seed: int
    hostile: CaseScore
    authorised: CaseScore

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-ready copy."""
        return {
            "seed": self.seed,
            "hostile_leads": self.hostile.uniquely_leads,
            "hostile_lead": self.hostile.lead,
            "hostile_facts": self.hostile.n_facts,
            "authorised_false_alarms": self.authorised.false_alarms,
            "authorised_facts": self.authorised.n_facts,
            "authorised_lead": self.authorised.lead,
        }


def false_alarm_count(*, silent: bool, concerns_write: bool, lead: str) -> int:
    """Return how many false-alarm narratives one authorised run produced.

    Silence is 0. Maintenance about the authorised write is 0. A narrative that does not
    concern the write counts. So does any other narrative about the write.

    Args:
        silent: The run promoted no command-effect fact and raised no narrative.
        concerns_write: The narrative's facts name the written setpoint.
        lead: The narrative's leading template id. Ignored when ``silent``.

    Returns:
        0 or 1. These runs raise at most one narrative.
    """
    if silent:
        return 0
    if concerns_write and lead == ENGINEERING_MAINTENANCE_TEMPLATE_ID:
        return 0
    return 1


def held_back_allowed(*, output_exists: bool, declaration_in_head: bool) -> bool:
    """Return whether a held-back score may be written.

    The output must not already exist, and the declaration commit must already be HEAD.
    A second call, or a call before that commit, is refused.
    """
    return not output_exists and declaration_in_head


def run_case(seed: int, *, kind: str) -> PlantRun:
    """Run one water-plant case in memory.

    Args:
        seed: Development or, after declaration, held-back seed.
        kind: ``hostile`` or ``authorised``.

    Returns:
        The completed run. The issuer is the declared operator.

    Raises:
        ValueError: If ``kind`` is neither, or the seed is in neither declared block.
    """
    if kind not in {"hostile", "authorised"}:
        raise ValueError(f"kind must be 'hostile' or 'authorised', got {kind!r}")
    if seed not in TRUSTED_DEVELOPMENT_SEEDS and seed not in TRUSTED_HELD_BACK_SEEDS:
        raise ValueError(f"seed {seed} is not a lane T seed")
    spec = _spec(seed)
    value = HOSTILE_SETPOINT if kind == "hostile" else AUTHORISED_SETPOINT
    network = WATER_DESCRIPTION.control_network
    if network is None:
        raise ValueError("water-treatment declares no control network")
    commands = PlannedCommandSource(
        {
            WRITE_AT: (
                PlannedWrite(
                    issuer=network.operator,
                    signal=LEVEL_SETPOINT,
                    value=value,
                    reason=f"lane T {kind} known-operator write",
                ),
            )
        }
    )
    injection = _injection(spec, commands, hide=kind == "hostile")
    return run_plant(PLANT_ID, spec, injection=injection, commands=commands)


def run_quiet(seed: int) -> PlantRun:
    """Run the same hold with no write, so a caller can see that the write moved the plant.

    Args:
        seed: A lane T seed. The hold matches `run_case`. There is no operator write.

    Returns:
        The completed run.
    """
    if seed not in TRUSTED_DEVELOPMENT_SEEDS and seed not in TRUSTED_HELD_BACK_SEEDS:
        raise ValueError(f"seed {seed} is not a lane T seed")
    spec = _spec(seed)
    return run_plant(PLANT_ID, spec, injection=_hold(spec), commands=NoCommands())


def score_case(
    run: PlantRun,
    *,
    kind: str,
    enabled: frozenset[str] = _H1,
) -> CaseScore:
    """Promote H1 and say whether unauthorised uniquely led.

    Args:
        run: A run from `run_case`.
        kind: ``hostile`` or ``authorised``. ``authorised`` is the false-alarm run.
        enabled: Which command-effect features to promote. Defaults to H1.

    Returns:
        The case score. Hostile runs report ``false_alarms`` 0; that column is for authorised.

    Raises:
        ValueError: If the issuer is not the declared operator, or is the engineering workstation.
    """
    network = run.description.control_network
    if network is None:
        raise ValueError(f"{run.plant_id} declares no control network")
    issuer = network.operator
    if issuer == ENGINEERING:
        raise ValueError("lane T does not score the silent engineering workstation")
    issued = [command for step in run.steps for command in step.issued if command.issuer == issuer]
    if any(command.issuer == ENGINEERING for step in run.steps for command in step.issued):
        raise ValueError("an engineering write is not a lane T case")
    if len(issued) != 1:
        raise ValueError(f"expected one operator write, found {len(issued)}")
    entities = _entities(run.description)
    entity_of = {entity.name: entity.id for entity in entities}
    pair = _level_pair(run)
    reported = {key: run.reported(key) for key in (LEVEL_SETPOINT, pair.response, pair.actuator)}
    timestamps = tuple(step.timestamp for step in run.steps)
    evidence = command_effect_evidence(
        description=run.description,
        reported=reported,
        timestamps=timestamps,
        writes=tuple(OperatorWrite(item.step_index, item.signal, item.applied) for item in issued),
        operating_bands={
            LEVEL_SETPOINT: (LEVEL_SETPOINT_OPERATING_LOW, LEVEL_SETPOINT_OPERATING_HIGH)
        },
        covered=frozenset(),
        entity_of=entity_of,
        calibrator=_WEIGHT,
        learned_from_window=(timestamps[0], timestamps[-1]),
        enabled=enabled,
        active_kinds=tuple(
            step.active.kind if step.active is not None else None for step in run.steps
        ),
        manual_modes=_MANUAL_MODES,
    )
    lead, tied = _lead(evidence, entities)
    silent = not evidence
    concerns = (not silent) and all(
        entity_of[LEVEL_SETPOINT] in fact.entity_ids for fact in evidence
    )
    alarms = (
        false_alarm_count(silent=silent, concerns_write=concerns, lead=lead)
        if kind == "authorised"
        else 0
    )
    return CaseScore(
        kind=kind,
        issuer=issued[0].issuer,
        n_facts=len(evidence),
        lead="" if silent else lead,
        tied=() if silent else tied,
        uniquely_leads=((not silent) and lead == UNAUTHORISED_CONTROL_TEMPLATE_ID and not tied),
        false_alarms=alarms,
        concerns_write=concerns,
    )


def score_seed(seed: int, *, enabled: frozenset[str] = _H1) -> SeedScore:
    """Score the hostile write and the authorised run for one seed."""
    return SeedScore(
        seed=seed,
        hostile=score_case(run_case(seed, kind="hostile"), kind="hostile", enabled=enabled),
        authorised=score_case(
            run_case(seed, kind="authorised"), kind="authorised", enabled=enabled
        ),
    )


def score_development(
    seeds: Sequence[int] = TRUSTED_DEVELOPMENT_SEEDS,
    *,
    enabled: frozenset[str] = _H1,
) -> tuple[SeedScore, ...]:
    """Score development seeds. Held-back seeds are refused here.

    Raises:
        ValueError: If any seed is not a development seed.
    """
    allowed = frozenset(TRUSTED_DEVELOPMENT_SEEDS)
    if not set(seeds) <= allowed:
        raise ValueError("score_development refuses seeds outside 97801-97820")
    return tuple(score_seed(seed, enabled=enabled) for seed in seeds)


def render_development(
    rows: Sequence[SeedScore],
    *,
    heading: str = "Lane T H1 development",
    features: str = TOWARD_LIMIT_AGAINST_STATE,
) -> str:
    """Return the development table. Synthetic diagnosis, not a field rate."""
    leads = sum(1 for row in rows if row.hostile.uniquely_leads)
    alarms = sum(row.authorised.false_alarms for row in rows)
    rate = alarms / len(rows) if rows else 0.0
    lines = [
        f"# {heading}",
        "",
        f"Result name: `{RESULT_NAME}`.",
        "Simulated diagnosis. Not a field rate (ADR 0073). Not the frozen 0 of 16.",
        f"Features: `{features}`. Weight: Platt coefficient 0, intercept 0.",
        "",
        "| Seed | Hostile facts | Hostile lead | Unique lead | Authorised facts | False alarms |",
        "| --- | ---: | --- | --- | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row.seed} | {row.hostile.n_facts} | {row.hostile.lead or 'silence'} | "
            f"{row.hostile.uniquely_leads} | {row.authorised.n_facts} | "
            f"{row.authorised.false_alarms} |"
        )
    lines += [
        "",
        f"Hostile unique leads: {leads} of {len(rows)}.",
        f"False-alarm narratives per authorised run: {rate:.2f} ({alarms} of {len(rows)}).",
        "",
    ]
    return "\n".join(lines)


def challenger_sha256(root: Path | None = None) -> str:
    """Return the sha256 of the frozen challenger files, in `CHALLENGER_FILES` order.

    The path is mixed in before the bytes so a rename is a different challenger. The
    declaration ADR is not in the set.
    """
    base = Path.cwd() if root is None else root
    digest = hashlib.sha256()
    for relative in CHALLENGER_FILES:
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update((base / relative).read_bytes())
    return digest.hexdigest()


def score_held_back() -> tuple[SeedScore, ...]:
    """Score seeds 97901-97920. The caller refuses a second write.

    This function does not look at the output file. The script does, and it refuses when
    the file exists or the declaration is not the HEAD commit.

    Raises:
        ValueError: If a seed were outside the held-back block. The block is fixed here.
    """
    return tuple(score_seed(seed, enabled=CHALLENGER_FEATURES) for seed in TRUSTED_HELD_BACK_SEEDS)


def render_held_back(rows: Sequence[SeedScore], *, tests_green: bool) -> str:
    """Return the held-back report, including each bar as met or not met.

    The bar wording is the declaration's. A rate of 0.20 is not above 0.20.
    """
    body = render_development(
        rows,
        heading="Lane T held-back",
        features="toward_limit_against_state, write_and_hide",
    )
    leads = sum(1 for row in rows if row.hostile.uniquely_leads)
    alarms = sum(row.authorised.false_alarms for row in rows)
    rate = alarms / len(rows) if rows else 0.0
    lead_bar = "met" if leads > 0 else "not met"
    alarm_bar = "met" if rate <= 0.20 else "not met"
    test_bar = "met" if tests_green else "not met"
    extra = [
        "## Bars",
        "",
        (
            "Hostile known-station writes led in more than 0 of them: "
            f"{leads} of {len(rows)}. {lead_bar}."
        ),
        (
            "False-alarm narratives per authorised run not above 0.20: "
            f"{rate:.2f} ({alarms} of {len(rows)}). {alarm_bar}."
        ),
        f"Known-link both-support tests green: {test_bar}.",
        "",
        "Simulated diagnosis. The harness cannot be believed as a field rate (ADR 0073). "
        "These numbers are not the frozen known-station 0 of 16 or the unknown-master 1 of 4, "
        "and they are not ≥70%.",
        "",
    ]
    return body + "\n".join(extra)


def _spec(seed: int) -> RunSpec:
    """Return the fixed-length run spec for ``seed``."""
    return RunSpec(
        seed=seed,
        start=_START,
        duration=_N_STEPS * _SAMPLE,
        sample_interval=_SAMPLE,
    )


def _injection(
    spec: RunSpec, commands: PlannedCommandSource, *, hide: bool
) -> HoldActuator | CompositeInjection:
    """Hold the intake until the write. A hostile run also freezes the clearwell report.

    The frozen value is the last honest report, taken from a probe that has not opened the
    reading window yet. Steps before the write match that probe.
    """
    held = _hold(spec)
    if not hide:
        return held
    probe = run_plant(PLANT_ID, spec, injection=held, commands=commands)
    frozen = probe.reported(CLEARWELL_LEVEL)[WRITE_AT - 1]
    window = TimeWindow(start=spec.instant(WRITE_AT), end=spec.instant(_N_STEPS))
    return CompositeInjection(
        parts=(held, HoldReading(signal=CLEARWELL_LEVEL, value=frozen, window=window))
    )


def _hold(spec: RunSpec) -> HoldActuator:
    """Hold the intake low until the write, so the clearwell falls short of its setpoint."""
    return HoldActuator(
        actuator=_INTAKE,
        value=_HOLD_INTAKE,
        window=TimeWindow(start=spec.start, end=spec.instant(WRITE_AT)),
    )


def _level_pair(run: PlantRun) -> CommandResponsePair:
    """Return the declared level loop: setpoint, actuator, and measurement."""
    for pair in declared_pairs(run.description):
        if pair.command == LEVEL_SETPOINT:
            return pair
    raise ValueError("water-treatment declares no level control pair")


def _entities(description: PlantDescription) -> tuple[Entity, ...]:
    """One entity per declared signal. The id is the plant and the signal, nothing else."""
    return tuple(
        Entity(
            id=f"ent_{description.plant_id}_{spec.key}",
            type=EntityType.PLC,
            domain=Domain.ATLAS,
            name=spec.key,
        )
        for spec in description.signals
    )


def _lead(evidence: Sequence[Evidence], entities: Sequence[Entity]) -> tuple[str, tuple[str, ...]]:
    """Return the narrative lead and any tied template ids.

    An empty evidence list is silence: the lead is the residual and the tie is empty, and the
    caller treats that as no narrative.
    """
    if not evidence:
        return INSUFFICIENT_EVIDENCE_TEMPLATE_ID, ()
    store = InMemoryEvidenceStore()
    for entity in entities:
        store.add_entity(entity)
    engine = ReasoningEngine(atlas_library(), store, ReasoningConfig())
    engine.ingest(evidence)
    ranked = engine.competing(Domain.ATLAS)
    tied = tied_lead_ids(ranked)
    return ranked[0].template_id, tied
