"""Answer U3's four diagnostic questions as SYNTHETIC-DERIVED output.

Everything this script prints is diagnostic output on a plant we simulated, against an adversary
we wrote. It is not a detection claim, not a lead rate, and is never compared to the frozen
known-station 0/16 or unknown-master 1/4. Nothing is appended to eval_runs/log.jsonl.

Question 4 is reported in structural terms only: which explanation leads, whether the lead is a
tie, whether ``insufficient_evidence`` is raised, whether the competing set shrinks when the
capture is withheld. No hypothesis confidence is printed.

Gate 1's fit-history safeguard is enforced before Atlas learns anything.
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NamedTuple

from phos.atlas.cmms import SAP_PM_SCHEMA, load_work_order_export, observations_from_work_orders
from phos.atlas.templates import atlas_library
from phos.atlas.work_orders import WorkOrderFact, promote_work_orders
from phos.breaking.commands import CommandPath, classify_command_issuer, read_command_path
from phos.ontology import Evidence, InMemoryEvidenceStore, Observation
from phos.reasoning.belief import rank_hypotheses, tied_lead_ids
from phos.reasoning.calibration import FittedPlattCalibrator
from phos.reasoning.engine import ReasoningEngine
from phos.reasoning.templates import INSUFFICIENT_EVIDENCE_TEMPLATE_ID
from phos.synth.command import Authorisation, IssuedCommand
from phos.synth.diagnostic_scenarios import DiagnosticKind, construct, run_scenario
from phos.synth.fit_history import assert_fit_history, required_fit_history
from phos.synth.maintenance import write_sap_pm_export
from phos.synth.plant import SYNTHETIC_DERIVED_BANNER, RunSpec
from phos.synth.run import PlantRun, run_plant
from phos.synth.traffic import TrafficPolicy, modbus_frames, write_pcap

PLANT = "water-treatment"
ASSETS = ("intake", "dosing", "filtration", "clearwell", "distribution")
CERTAIN = FittedPlattCalibrator(coefficient=0.0, intercept=40.0)
_START = datetime(2026, 3, 1, tzinfo=UTC)
_REPORT = Path("eval_runs/synth/u3-diagnostic.md")


class Story(NamedTuple):
    """A command-path view with no confidence numbers."""

    n_graph_findings: int
    n_live_features: int
    n_evidence: int
    competing: tuple[str, ...]
    tied_leaders: tuple[str, ...]
    unique_leader: str | None
    insufficient_leads: bool


def _commit() -> str:
    """Return HEAD, or ``unknown`` if git is unavailable."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _capture(run: PlantRun, path: Path, seed: int) -> int:
    """Write ``run``'s control traffic, including planned dropouts, to ``path``."""
    frames = modbus_frames(
        run.description,
        run.steps,
        TrafficPolicy(seed=seed),
        dropouts=run.realism.dropouts,
    )
    return write_pcap(frames, path)


def _fit_spec(seed: int) -> RunSpec:
    """Return a declared-normal stretch that satisfies Gate 1 for water treatment."""
    hours = required_fit_history(PLANT).hours
    duration = timedelta(hours=hours)
    assert_fit_history(PLANT, duration)
    return RunSpec(
        seed=seed,
        start=_START,
        duration=duration,
        sample_interval=timedelta(seconds=30),
    )


def _reason(facts: Sequence[Evidence], observations: Sequence[Observation]) -> Story:
    """Reason over already-promoted facts. Returns template ids, never confidences."""
    store = InMemoryEvidenceStore()
    for observation in observations:
        store.add_observation(observation)
    for fact in facts:
        store.add_evidence(fact)
    engine = ReasoningEngine(atlas_library(), store)
    engine.ingest(facts)
    ranked = rank_hypotheses(engine.hypotheses())
    templates = tuple(item.template_id for item in ranked)
    tied = tied_lead_ids(ranked)
    unique = None if tied else (templates[0] if templates else None)
    return Story(
        n_graph_findings=0,
        n_live_features=0,
        n_evidence=len(facts),
        competing=templates,
        tied_leaders=tied,
        unique_leader=unique,
        insufficient_leads=unique == INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    )


def story_from_path(path: CommandPath) -> Story:
    """Promote a command path and return a structural competing-set view."""
    bundle = path.promote(CERTAIN)
    observations: list[Observation] = [item.observation for item in bundle.departures]
    observations.extend(item.finding for item in bundle.changes)
    reasoned = _reason(bundle.evidence(), observations)
    return reasoned._replace(
        n_graph_findings=len(path.graph_findings),
        n_live_features=len(path.live_features),
    )


def story_from_work_orders(facts: Sequence[WorkOrderFact]) -> Story:
    """Reason over promoted work-order facts alone."""
    reasoned = _reason(
        tuple(item.evidence for item in facts),
        tuple(item.observation for item in facts),
    )
    return reasoned


def more_uncertain(present: Story, removed: Story) -> bool:
    """Return whether withholding evidence made the command story thinner or silent."""
    if present.unique_leader is not None and removed.unique_leader is None:
        return True
    if (
        present.unique_leader is not None
        and removed.insufficient_leads
        and not present.insufficient_leads
    ):
        return True
    if present.n_evidence > removed.n_evidence:
        return True
    if present.n_graph_findings > removed.n_graph_findings:
        return True
    return False


def more_confident_with_less(present: Story, removed: Story) -> bool:
    """Return whether withholding evidence minted a unique contentful leader.

    A unique ``insufficient_evidence`` lead after removal is more uncertain, not more confident.
    """
    if removed.unique_leader is None or removed.insufficient_leads:
        return False
    if present.unique_leader is None or present.insufficient_leads:
        return True
    return False


def competing_names(story: Story) -> str:
    """Return unique template ids plus the hypothesis count. Never confidence."""
    names = list(dict.fromkeys(story.competing))
    if not names:
        return "silent (0 hypotheses)"
    return f"{names} ({len(story.competing)} hypotheses)"


def overlap_on_seed(seed: int) -> bool:
    """Return whether the adversary found a sanctioned window on ``seed``."""
    scenario = construct(DiagnosticKind.ATTACKER_DURING_MAINTENANCE, seed)
    return any(
        item.endswith("True")
        for item in scenario.ground_truth
        if item.startswith("overlap_on_this_seed=")
    )


Q3_SEARCH_SEEDS: tuple[int, ...] = (7, 11, 13, 17, 19, 23)


def _write_report(lines: list[str], path: Path) -> None:
    """Write ``lines`` to ``path``, creating parents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _issued(run: PlantRun) -> list[IssuedCommand]:
    """Return every command the plant actually issued."""
    return [command for step in run.steps for command in step.issued]


def main(argv: Sequence[str] | None = None) -> int:
    """Run the four questions and write the diagnostic report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--output", type=Path, default=_REPORT)
    args = parser.parse_args(argv)

    commit = _commit()
    command = f"uv run python scripts/diagnose_u3_environment.py --seed {args.seed}"
    required = required_fit_history(PLANT)
    lines: list[str] = [
        f"# {SYNTHETIC_DERIVED_BANNER}",
        "",
        "Not a measurement. Not a detection claim. Not a row in `eval_runs/log.jsonl`.",
        "Not evidence about a real plant. Frozen command-lead 0/16 and 1/4 are untouched.",
        "",
        f"- seed: `{args.seed}`",
        f"- commit: `{commit}`",
        f"- reproduce: `{command}`",
        f"- plant: `{PLANT}`",
        f"- fit history: `{required.hours:g} h` ({required.name})",
        "",
    ]

    fit_spec = _fit_spec(args.seed)
    ordinary = construct(DiagnosticKind.ORDINARY_OPERATION, args.seed)
    unauth = construct(DiagnosticKind.UNAUTHORISED_COMMANDS, args.seed)
    maint = construct(DiagnosticKind.MAINTENANCE, args.seed)

    fit_run = run_plant(PLANT, fit_spec)
    ordinary_run = run_scenario(ordinary)
    unauth_run = run_scenario(unauth)

    with tempfile.TemporaryDirectory(prefix="phos-u3-diag-") as raw:
        workdir = Path(raw)
        baseline = workdir / "fit.pcap"
        ordinary_pcap = workdir / "ordinary.pcap"
        unauth_pcap = workdir / "unauth.pcap"
        _capture(fit_run, baseline, args.seed)
        _capture(ordinary_run, ordinary_pcap, args.seed)
        _capture(unauth_run, unauth_pcap, args.seed)

        unauth_from_unauth = [
            c for c in _issued(unauth_run) if c.authorised is Authorisation.UNAUTHORISED
        ]
        unauth_from_ordinary = [
            c for c in _issued(ordinary_run) if c.authorised is Authorisation.UNAUTHORISED
        ]
        unauth_path = read_command_path(baseline, unauth_pcap)
        ordinary_path = read_command_path(baseline, ordinary_pcap)
        kind = classify_command_issuer("scada", unauth_run.description, unauth_path.graph)
        q1_yes = bool(unauth_from_unauth) and bool(
            unauth_path.graph_findings or unauth_path.live_features
        )
        lines += [
            "## 1. Does command attribution function when command evidence genuinely exists?",
            "",
            f"- control (ordinary operation): unauthorised writes = `{len(unauth_from_ordinary)}` "
            f"(can come out zero: `{not unauth_from_ordinary}`)",
            f"- treatment (unauthorised scada write): unauthorised writes = "
            f"`{len(unauth_from_unauth)}`",
            f"- command-path findings on unauthorised capture: `{len(unauth_path.graph_findings)}`",
            f"- command-path findings on ordinary capture: `{len(ordinary_path.graph_findings)}`",
            f"- issuer `scada` classified as: `{kind.value}` "
            "(known-station vs unknown-master, unpooled)",
            (
                "- answer: `yes, the path sees the writes`"
                if q1_yes
                else "- answer: `no, the path is silent`"
            ),
            "- not a lead rate. not 0/16. not 1/4.",
            "",
        ]

        export = workdir / "sap_pm.csv"
        promoted: list[WorkOrderFact] = []
        n_orders = 0
        n_sanctioning = 0
        if maint.calendar is not None:
            write_sap_pm_export(maint.calendar, export)
            n_orders = len(maint.calendar.orders)
            n_sanctioning = len(maint.calendar.sanctioning())
            records = load_work_order_export(export, SAP_PM_SCHEMA, declared_assets=ASSETS)
            promoted = promote_work_orders(observations_from_work_orders(records), CERTAIN)
        wo_story = story_from_work_orders(promoted)
        withheld = story_from_work_orders(())
        lines += [
            "## 2. Does maintenance evidence move the competing hypotheses, "
            "and in which direction?",
            "",
            f"- control (export withheld): promoted facts = `{withheld.n_evidence}` "
            f"(can come out zero: `{withheld.n_evidence == 0}`)",
            f"- treatment (SAP PM export): orders raised = `{n_orders}`, "
            f"sanctioning = `{n_sanctioning}`, promoted facts = `{len(promoted)}`",
            f"- competing set with the export: `{competing_names(wo_story)}`",
            f"- unique leader with the export: "
            f"`{wo_story.unique_leader or 'none (tie or silent)'}`",
            f"- unique leader with the export withheld: "
            f"`{withheld.unique_leader or 'none (tie or silent)'}`",
            (
                "- answer: `yes, the inlet promotes facts`"
                if promoted
                else "- answer: `no, nothing was promoted`"
            ),
            "- direction: work-order facts support engineering_maintenance and contradict "
            "unauthorised_control_activity (ADR 0069). This script does not retune templates.",
            "- wiring result, not a queue improvement.",
            "",
        ]

        searched = {seed: overlap_on_seed(seed) for seed in Q3_SEARCH_SEEDS}
        control_overlap = searched.get(args.seed, overlap_on_seed(args.seed))
        hit = next((seed for seed, flag in searched.items() if flag), None)
        n_issued = 0
        n_covered = 0
        if hit is not None:
            inspectable = construct(DiagnosticKind.ATTACKER_DURING_MAINTENANCE, hit)
            inspectable_run = run_scenario(inspectable)
            issued_covered = _issued(inspectable_run)
            n_issued = len(issued_covered)
            if inspectable.calendar is not None:
                moments = [c.timestamp for c in issued_covered]
                n_covered = len(inspectable.calendar.covered_windows({"clearwell": moments}))
        if n_covered:
            q3_answer = "adversary wrote inside a sanctioned window; the case is inspectable"
        elif n_issued:
            q3_answer = "adversary chose a window and wrote, but the write missed the covering test"
        else:
            q3_answer = "no overlap in the searched seeds"
        lines += [
            "## 3. What happens when an attacker uses legitimate credentials "
            "inside a sanctioned window?",
            "",
            "- construction: the adversary is given an independently planned calendar "
            "and chooses a window. The calendar is not moved to cover the attack. "
            "Natural overlap is a seed search, reported as method, not a calendar that "
            "was walked onto the attack.",
            f"- seeds searched: `{list(Q3_SEARCH_SEEDS)}`",
            f"- overlap by seed: `{searched}`",
            f"- control (seed {args.seed} has no overlap): `{not control_overlap}`",
            f"- first overlapping seed: `{hit}`",
            f"- attacker writes issued on that seed: `{n_issued}`",
            f"- falling inside a sanctioned clearwell window: `{n_covered}`",
            "- Atlas then has, when the write is covered: an unauthorised write in the ground "
            "truth, a graph finding, AND a covering work order. ADR 0014 still holds: the bytes "
            "are the same.",
            f"- answer: `{q3_answer}`",
            "",
        ]

        present = story_from_path(unauth_path)
        removed = story_from_work_orders(())
        ordinary_story = story_from_path(ordinary_path)
        silent_when_removed = more_uncertain(present, removed)
        grew_confident = more_confident_with_less(present, removed)
        lines += [
            "## 4. Does Atlas become MORE uncertain when evidence is removed?",
            "",
            "Paired runs, same seed, unauthorised-commands scenario. Capture present vs capture "
            "withheld (the incomplete-observations lever: no live pcap, so no command facts are "
            "ingested; the residual remains). Structural terms only. No confidence numbers.",
            "",
            f"- with live capture: unique leader "
            f"`{present.unique_leader or 'none (tie or silent)'}`, "
            f"tied leaders `{list(present.tied_leaders) or 'none'}`, "
            f"competing `{competing_names(present)}`, "
            f"graph findings `{present.n_graph_findings}`, "
            f"command evidence `{present.n_evidence}`",
            f"- capture withheld: unique leader "
            f"`{removed.unique_leader or 'none (tie or silent)'}`, "
            f"tied leaders `{list(removed.tied_leaders) or 'none'}`, "
            f"competing `{competing_names(removed)}`, "
            f"command evidence `{removed.n_evidence}`",
            f"- ordinary-operation control: unique leader "
            f"`{ordinary_story.unique_leader or 'none (tie or silent)'}`, "
            f"graph findings `{ordinary_story.n_graph_findings}`, "
            f"command evidence `{ordinary_story.n_evidence}` "
            "(graph findings can come out zero: a yes that cannot fail is meaningless)",
            f"- more uncertain when evidence is removed: `{silent_when_removed}`",
            f"- more confident with less evidence (a break): `{grew_confident}`",
            "",
            "A unique contentful command story that appears only after the capture is removed "
            "would be a break. Changing engine behaviour to chase a prettier answer is outside U3.",
            "",
            "## What this is not",
            "",
            "- A detection claim.",
            "- A row in `eval_runs/log.jsonl`.",
            "- A reason to quote 0/16 or 1/4.",
            "- Evidence about a real plant (ADR 0029, ADR 0073, register R4).",
            "",
        ]

    _write_report(lines, args.output)
    print("\n".join(lines))
    print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
