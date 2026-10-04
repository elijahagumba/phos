"""Run one simulated incident through Atlas, end to end, and keep what a person needs to read.

This is the path behind ``phos demo``. Nothing in it is staged: a simulated water plant runs for the
history Gate 1 requires, its control traffic is written to a capture, a second run carries the
incident, Atlas learns the first capture and reads the second, and the reasoning engine writes the
brief U4 renders. What the demo shows is what that path produced.

Two choices are the demo's, and both follow ``scripts/diagnose_u3_environment.py``:

* **Every departure is promoted at full weight.** A calibrator needs labelled positives and the
  demo has none, so it uses the same certain calibrator U3 does. The brief never shows a
  confidence, but weights still feed the belief update, so this choice can change whether an
  explanation overtakes the residual and therefore the assessment itself. The placeholder priors
  and evidence strength (ADR 0008) matter as much: on a write from a never-seen device, the
  residual still leads. Those priors are not retuned here.
* **Command behaviour is an empirical quantile band** (ADR 0086), not the Gaussian baseline.
  Interval and count features pile up on exact values a three-sigma band excludes. The Gaussian
  model remains in the tree and still produces the frozen rows; only this demo fits the
  empirical one.
* **Each capture is read once.** `phos.breaking.read_command_path` reads the baseline twice;
  here the dissected frames are kept and handed to the same functions, which produces identical
  evidence in about two thirds of the time.

Ground truth is read from the run after Atlas has finished, from the commands the plant actually
issued and the write authority it declared. It is never an input to anything Atlas does.

SYNTHETIC-DERIVED: a plant we simulated, an adversary we wrote. A demonstration, not a measurement.
"""

from __future__ import annotations

import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Final

from phos.atlas import (
    compare_to_graph,
    default_registry,
    dissect_capture,
    featurise_commands,
    learn_device_command_graph,
)
from phos.atlas.command_evidence import CommandDeparture, GraphChange
from phos.atlas.templates import atlas_library
from phos.breaking import CommandPath
from phos.models import BehaviouralModel, EmpiricalBaseline
from phos.ontology import InMemoryEvidenceStore, Narrative
from phos.reasoning import FittedPlattCalibrator, ReasoningEngine
from phos.reasoning.analyst import NarrativeBrief, assess_narrative
from phos.synth.command import Authorisation, IssuedCommand
from phos.synth.diagnostic_scenarios import DiagnosticKind, construct, run_scenario
from phos.synth.fit_history import assert_fit_history, required_fit_history
from phos.synth.plant import PlantDescription, RunSpec
from phos.synth.run import PlantRun, run_plant
from phos.synth.traffic import TrafficPolicy, modbus_frames, write_pcap

__all__ = [
    "PLANT",
    "DemoResult",
    "Scenario",
    "Stage",
    "describe_change",
    "describe_departure",
    "describe_truth",
    "run_demo",
]

PLANT: Final = "water-treatment"
"""The one plant with a control network, a write policy and a maintenance planner."""

_START: Final = datetime(2026, 3, 1, tzinfo=UTC)
_SAMPLE_INTERVAL: Final = timedelta(seconds=30)
_CERTAIN: Final = FittedPlattCalibrator(coefficient=0.0, intercept=40.0)


class Scenario(str, Enum):
    """The incidents the demo can stage, each one of U3's diagnostic kinds.

    Attributes:
        UNAUTHORISED: The SCADA server writes a setpoint only the control-room HMI may write.
        OPERATOR: The HMI makes a write it is allowed to make, during an operator intervention.
        ATTACKER: The adversary catalogue's attacker works the plant.
    """

    UNAUTHORISED = "unauthorised"
    OPERATOR = "operator"
    ATTACKER = "attacker"

    @property
    def kind(self) -> DiagnosticKind:
        """Return the U3 diagnostic kind this scenario runs."""
        return {
            Scenario.UNAUTHORISED: DiagnosticKind.UNAUTHORISED_COMMANDS,
            Scenario.OPERATOR: DiagnosticKind.LEGITIMATE_OPERATOR,
            Scenario.ATTACKER: DiagnosticKind.ATTACKER_ACTIVITY,
        }[self]


@dataclass(frozen=True)
class Stage:
    """One step of the run, reported as it finishes."""

    name: str
    detail: str
    seconds: float


@dataclass(frozen=True)
class DemoResult:
    """Everything the demo prints, already in plain words.

    Attributes:
        scenario: Which incident ran.
        seed: The seed every run and capture used.
        plant_label: The simulated plant's name.
        stages: The run's steps, in order.
        subject: Who the brief is about, e.g. ``"SCADA server → Clearwell PLC"``. Empty when Atlas
            raised nothing.
        brief: The brief Atlas wrote for the incident it saw, or ``None`` if it saw nothing.
        findings: What Atlas saw, one plain sentence per fact on the brief's narrative.
        other_incidents: How many further narratives the run produced besides the one shown.
        truth: What the plant actually did, read from the run after Atlas finished.
        writes: How many writes the plant actually received.
        unauthorised: Whether any write in the run broke the plant's declared write policy.
        concerns_truth: Whether the incident shown involves a write that actually happened: a fact
            about the writing device, or the link it wrote on, in the minute it wrote. Decided
            after Atlas finished, and never used to choose which incident is shown.
    """

    scenario: Scenario
    seed: int
    plant_label: str
    stages: tuple[Stage, ...]
    subject: str
    brief: NarrativeBrief | None
    findings: tuple[str, ...]
    other_incidents: int
    truth: tuple[str, ...]
    writes: int
    unauthorised: bool
    concerns_truth: bool


def demo_command_baseline(baseline: BehaviouralModel | None = None) -> BehaviouralModel:
    """Return the command-behaviour model the demo fits.

    The demo uses `EmpiricalBaseline` (ADR 0086). A measurement of the Gaussian path may pass
    that model instead. The ``phos demo`` command does not expose the choice, and neither call
    changes template priors or evidence strength.

    Args:
        baseline: A model to fit in place of the empirical default, or ``None`` for the default.

    Returns:
        The model `run_demo` fits on command features.
    """
    return EmpiricalBaseline() if baseline is None else baseline


def run_demo(
    scenario: Scenario = Scenario.UNAUTHORISED,
    seed: int = 11,
    on_stage: Callable[[Stage], None] | None = None,
    behaviour: BehaviouralModel | None = None,
) -> DemoResult:
    """Run ``scenario`` through Atlas and return what a person needs to read.

    Args:
        scenario: The incident to stage.
        seed: Seeds both plant runs and both captures.
        on_stage: Called as each step finishes, so a terminal can show progress.
        behaviour: Command-behaviour model to fit. ``None`` selects `EmpiricalBaseline`.
            Passed only by the ADR 0086 measurement; the command line does not set it.
            Named apart from the baseline capture this function dissects.

    Returns:
        The result, with ground truth read only after Atlas has written its brief.
    """
    command_model = demo_command_baseline(behaviour)
    stages: list[Stage] = []
    clock = time.perf_counter()

    def finish(name: str, detail: str) -> None:
        nonlocal clock
        now = time.perf_counter()
        stage = Stage(name=name, detail=detail, seconds=now - clock)
        clock = now
        stages.append(stage)
        if on_stage is not None:
            on_stage(stage)

    fit_hours = required_fit_history(PLANT).hours
    fit_duration = timedelta(hours=fit_hours)
    assert_fit_history(PLANT, fit_duration)
    fit_run = run_plant(
        PLANT,
        RunSpec(seed=seed, start=_START, duration=fit_duration, sample_interval=_SAMPLE_INTERVAL),
    )
    staged = construct(scenario.kind, seed)
    live_run = run_scenario(staged)
    description = fit_run.description
    finish("Simulating", f"{fit_hours:g} hours of ordinary operation")

    with tempfile.TemporaryDirectory(prefix="phos-demo-") as raw:
        workdir = Path(raw)
        baseline_capture = _capture(fit_run, workdir / "baseline.pcap", seed)
        live_capture = _capture(live_run, workdir / "live.pcap", seed)
        registry = default_registry()
        baseline = list(dissect_capture(baseline_capture, registry))
        graph = learn_device_command_graph(baseline)
        fitted = command_model.fit(featurise_commands(baseline))
        devices = len(description.control_network.nodes) if description.control_network else 0
        finish("Learning", f"{len(baseline):,} control messages between {devices} devices")

        live = list(dissect_capture(live_capture, registry))
        path = CommandPath(
            live_features=tuple(featurise_commands(live)),
            graph_findings=tuple(compare_to_graph(graph, live)),
            graph=graph,
            fitted=fitted,
        )
    live_hours = staged.spec.duration / timedelta(hours=1)
    finish("Watching", f"{live_hours:g} hours of live traffic, {len(live):,} messages")

    bundle = path.promote(_CERTAIN)
    store = InMemoryEvidenceStore()
    for departure in bundle.departures:
        store.add_observation(departure.observation)
    for change in bundle.changes:
        store.add_observation(change.finding)
    facts = bundle.evidence()
    for fact in facts:
        store.add_evidence(fact)
    library = atlas_library()
    engine = ReasoningEngine(library, store)
    engine.ingest(facts)
    for hypothesis in engine.hypotheses():
        store.add_hypothesis(hypothesis)
    narratives = engine.narratives()
    for narrative in narratives:
        store.add_narrative(narrative)
    shown = _largest(narratives)
    brief = assess_narrative(shown, store, library) if shown is not None else None
    explanations = len(brief.explanations) if brief is not None else 0
    finish("Reasoning", f"{len(facts)} facts, {explanations} explanations")

    labels = _device_labels(description)
    cited = set(shown.evidence_ids) if shown is not None else set()
    findings = [
        describe_departure(item, labels, fit_hours)
        for item in bundle.departures
        if item.evidence.id in cited
    ]
    findings += [
        describe_change(item, labels, fit_hours)
        for item in bundle.changes
        if item.evidence.id in cited
    ]
    issued = [command for step in live_run.steps for command in step.issued]
    return DemoResult(
        scenario=scenario,
        seed=seed,
        plant_label=description.label,
        stages=tuple(stages),
        subject=_subject(bundle.departures, bundle.changes, cited, labels),
        brief=brief,
        findings=tuple(findings),
        other_incidents=max(len(narratives) - 1, 0),
        truth=describe_truth(issued, description),
        writes=len(issued),
        unauthorised=any(c.authorised is Authorisation.UNAUTHORISED for c in issued),
        concerns_truth=_concerns(bundle.departures, bundle.changes, cited, issued, description),
    )


def _capture(run: PlantRun, path: Path, seed: int) -> Path:
    """Write ``run``'s control traffic, planned dropouts included, to ``path``."""
    frames = modbus_frames(
        run.description, run.steps, TrafficPolicy(seed=seed), dropouts=run.realism.dropouts
    )
    write_pcap(frames, path)
    return path


def _largest(narratives: Sequence[Narrative]) -> Narrative | None:
    """Return the narrative citing the most evidence, the first on a tie."""
    if not narratives:
        return None
    return max(narratives, key=lambda narrative: len(narrative.evidence_ids))


def _device_labels(description: PlantDescription) -> dict[str, str]:
    """Map each device address on the plant's control network to its declared name."""
    if description.control_network is None:
        return {}
    return {node.ip: node.label for node in description.control_network.nodes}


def _subject(
    departures: Sequence[CommandDeparture],
    changes: Sequence[GraphChange],
    cited: set[str],
    labels: dict[str, str],
) -> str:
    """Name who the incident is about: issuer and target if a link changed, else the device."""
    for change in changes:
        if change.evidence.id in cited:
            context = change.finding.context
            issuer = labels.get(context.get("issuer_ip", ""), context.get("issuer_ip", "?"))
            target = labels.get(context.get("target_ip", ""), context.get("target_ip", "?"))
            return f"{issuer} → {target}"
    for departure in departures:
        if departure.evidence.id in cited:
            address = departure.observation.context.get("device_ip", "")
            return labels.get(address, address)
    return ""


def _within(context: dict[str, str], moment: datetime) -> bool:
    """Return whether ``moment`` falls in an observation's window, allowing one minute of slack.

    The capture jitters each frame a few milliseconds past the sample it carries, so a write made
    on a window's boundary can land in the window that opens just after it.
    """
    start, end = context.get("window_start"), context.get("window_end")
    if start is None or end is None:
        return False
    slack = timedelta(minutes=1)
    return datetime.fromisoformat(start) - slack <= moment <= datetime.fromisoformat(end)


def _concerns(
    departures: Sequence[CommandDeparture],
    changes: Sequence[GraphChange],
    cited: set[str],
    issued: Sequence[IssuedCommand],
    description: PlantDescription,
) -> bool:
    """Return whether any cited fact is about a write that actually happened, when it happened."""
    network = description.control_network
    if network is None:
        return False
    address = {node.node_id: node.ip for node in network.nodes}
    for command in issued:
        issuer, target = address.get(command.issuer), address.get(command.target)
        for change in changes:
            context = change.finding.context
            if (
                change.evidence.id in cited
                and context.get("issuer_ip") == issuer
                and context.get("target_ip") == target
                and _within(context, command.timestamp)
            ):
                return True
        for departure in departures:
            context = departure.observation.context
            if (
                departure.evidence.id in cited
                and context.get("device_ip") == issuer
                and _within(context, command.timestamp)
            ):
                return True
    return False


def _seconds(milliseconds: float) -> str:
    """Format a duration in milliseconds as seconds with one decimal."""
    return f"{milliseconds / 1000:.1f} s"


def describe_departure(item: CommandDeparture, labels: dict[str, str], fit_hours: float) -> str:
    """Say in one sentence how a device's command behaviour left its learned band."""
    observation = item.observation
    expected = item.deviation.expected
    address = observation.context.get("device_ip", "")
    who = f"The {labels.get(address, address)}"
    low, high, value = max(expected.low, 0.0), max(expected.high, 0.0), observation.value
    feature = observation.feature
    if feature == "write_command_share":
        share = f"{value:.0%} of its commands in one minute were writes."
        if high == 0.0:
            return f"{who}: {share} In {fit_hours:g} hours it had sent none."
        return f"{who}: {share} Normally {low:.0%} to {high:.0%}."
    if feature == "command_interval_mean_ms":
        return (
            f"{who}: one command every {_seconds(value)} on average. "
            f"Normally every {_seconds(low)} to {_seconds(high)}."
        )
    if feature == "command_count":
        return f"{who}: {value:.0f} commands in one minute. Normally {low:.0f} to {high:.0f}."
    name = feature.replace("_", " ")
    return f"{who}: {name} was {value:g}. Normally {low:g} to {high:g}."


def describe_change(item: GraphChange, labels: dict[str, str], fit_hours: float) -> str:
    """Say in one sentence how who-commands-whom changed against the learned graph."""
    finding = item.finding
    context = finding.context
    issuer = labels.get(context.get("issuer_ip", ""), context.get("issuer_ip", "a device"))
    target = labels.get(context.get("target_ip", ""), context.get("target_ip", "a device"))
    if finding.feature == "unexpected_command_function":
        name = context.get("function_name", "an unknown function").replace("_", " ")
        code = context.get("function_code", "?")
        learned = [c for c in context.get("learned_function_codes", "").split(",") if c]
        carried = (
            f"function {learned[0]}"
            if len(learned) == 1
            else "functions " + ", ".join(learned[:-1]) + f" and {learned[-1]}"
            if learned
            else "nothing"
        )
        return (
            f"The {issuer} sent {name} (function {code}) to the {target}. "
            f"In {fit_hours:g} hours that link had only carried {carried}."
        )
    if finding.feature == "unknown_command_relationship":
        return (
            f"The {issuer} sent {finding.value:.0f} commands to the {target}. "
            f"In {fit_hours:g} hours it had never commanded it."
        )
    if finding.feature == "silent_command_relationship":
        return (
            f"The link from the {issuer} to the {target} went silent. It normally carries "
            f"about {finding.value:.0f} commands a minute."
        )
    return f"{finding.feature.replace('_', ' ')} between the {issuer} and the {target}."


def describe_truth(
    issued: Sequence[IssuedCommand], description: PlantDescription
) -> tuple[str, ...]:
    """Say what the plant was actually told to do, and whether its write policy allowed it."""
    if not issued:
        return ("No device wrote anything to the plant.",)
    names = (
        {node.node_id: node.label for node in description.control_network.nodes}
        if description.control_network is not None
        else {}
    )
    signals = {signal.key: signal.label.lower() for signal in description.signals}
    authority = description.write_authority
    grants = authority.grants if authority is not None else {}
    lines: list[str] = []
    seen: set[tuple[str, str, str, Authorisation]] = set()
    for command in issued:
        key = (command.issuer, command.target, command.signal, command.authorised)
        if key in seen:
            continue
        seen.add(key)
        who = names.get(command.issuer, command.issuer)
        where = names.get(command.target, command.target)
        what = signals.get(command.signal, command.signal)
        if command.authorised is Authorisation.AUTHORISED:
            verdict = "It is allowed to. Authorised."
        else:
            allowed = sorted(
                names.get(node, node) for node, keys in grants.items() if command.signal in keys
            )
            verdict = (
                f"Only the {' and the '.join(allowed)} may write it. Unauthorised."
                if allowed
                else "No device may write it. Unauthorised."
            )
        lines.append(f"The {who} wrote the {what} on the {where}. {verdict}")
    return tuple(lines)
