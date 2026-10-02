"""The report: the map, its two separate flavours, and the boundary on everything it says.

One report, regenerable, stamped with the commit and the seed that produced it. It carries four
things and keeps them apart on purpose:

1. **The clean breaking-point map** — per attack type, the subtlety at which Atlas crosses from
   caught to missed. The headline, and the only part that supports the sentence "Atlas detects
   plant attacks down to this subtlety".
2. **The fingerprint-caveated map** — the same reduction for attacks whose manipulation carries
   D2's documented statistical residual. Printed in its own section, under its own caveat, and
   never folded into the headline.
3. **The robustness results** — what the software did when handed corrupted input. Reported as
   robustness and never as detection, because an input-hostile case supports no claim whatever
   about security.
4. **The blind-spot summary** — the plain written answer to "where does Atlas go blind", which is
   what this whole arc was built to produce.

`BREAKING_HARNESS_CAVEATS` travels with all of it, into the rendered report and into the experiment
log, because a number that arrives without its boundary gets read without it.
"""

import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from phos.breaking.breakpoint import BreakingPoint, breaking_points
from phos.breaking.commands import ATTACK_TEMPLATE_ID, CommandIssuerKind, CommandReasoningResult
from phos.breaking.fingerprint import FINGERPRINT_CAVEAT, FingerprintStatus
from phos.breaking.harness import BreakingConfig, CorpusBreakdown
from phos.breaking.outcome import AttackOutcome, DetectionVerdict
from phos.breaking.robustness import CorpusRobustness
from phos.eval.report import (
    DEFAULT_SYNTH_SATURATION,
    append_to_experiment_log,
    apply_saturation_policy,
    current_git_commit,
)
from phos.ontology import UtcDatetime, utc_now
from phos.synth.attacks import (
    ATTACKS_ARE_OURS_CAVEAT,
    INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT,
)

__all__ = [
    "ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT",
    "BREAKING_HARNESS_CAVEATS",
    "DEFAULT_REPORT_DIR",
    "SATURATED_FP_PER_HOUR",
    "BreakingReport",
    "assemble",
    "render",
    "summary_json",
    "write_report",
]

logger = logging.getLogger(__name__)

DEFAULT_REPORT_DIR: Final = Path("eval_runs/breaking")
"""Where the machine-readable report is written. The experiment log is `phos.eval`'s own."""

_OUR_SIMULATION_CAVEAT: Final = (
    "These are attacks WE designed against a MODEL of a plant. A blind spot found here is real and "
    "worth fixing — the map's value is in its misses. But Atlas performing well here shows that "
    "it handles our adversary against our simulation, a necessary step toward handling a real "
    "adversary against a real plant and is not evidence of it. No number in this report may be "
    "quoted as a detection rate for Atlas in the field."
)

_FLAVOUR_CAVEAT: Final = (
    "Detection results and input-hostile results are measured and reported separately and are "
    "NEVER combined. Detection results support only 'Atlas detects plant attacks down to this "
    "subtlety'. Input-hostile results support only 'Atlas's software survives hostile input'. "
    "Neither, alone or together, supports any claim that PHOS is secure against an attacker."
)

_UNCALIBRATED_CAVEAT: Final = (
    "The hypothesis confidences behind the command-reasoning section are NOT calibrated "
    "probabilities and are not surfaced as any (Constitution §3.3). Only the ORDERING of competing "
    "explanations is read, and only the direction it moved."
)

ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT: Final = (
    "The command-attribution result is an ORDINAL RANK MEASURED AGAINST OUR OWN MATERIAL, and it "
    "may not be cited as a real-world detection rate. What it compares is where one named "
    "explanation sat before and after Atlas could read the commands — our attack library, run "
    "against our plant model, judged by our template set. Three things follow. It is not a rate: "
    "'moved in n of m' counts attacks in a hand-written battery, so its denominator is a property "
    "of what we chose to write and carries no population behind it. It is not calibrated: only the "
    "direction the ordering moved is read, never the confidence attached to it. And it is not "
    "transferable: a real commissioning engineer leaves behind the same new device relationship an "
    "intruder does, so no movement here says the two can be told apart in the field. Known-station "
    "writes and unknown-master writes must not be pooled into one lead rate: they test different "
    "template splits (ADR 0014 vs ADR 0027). Quoting this number as a detection rate would claim "
    "a measurement against reality that was never made."
)
"""The refusal that travels with the attribution rank, distinct from `ATTACKS_ARE_OURS_CAVEAT`.

That caveat bounds a *detection rate* measured on our library. This one bounds a quantity that is
not a rate at all, and whose most likely misuse is being read as one — see PART 6C's PROGRESS entry
for where a figure of this shape was already quoted without its denominator.
"""

SATURATED_FP_PER_HOUR: Final = 1.0
"""False positives per normal hour beyond which a recall row describes saturation, not detection.

Anchored on PART 2's own statement of what decides adoption — "three false alarms a shift is the
number that decides whether a system stays switched on", which is roughly 0.375 an hour. One an
hour is already several times that, so a corpus above it is not a detector anyone would keep
switched on, and its perfect recall means it alerted on nearly everything rather than that it saw
the attacks.
"""

_SATURATION_CAVEAT: Final = (
    "A corpus whose false-positive load is this high has not 'caught' its attacks in any useful "
    "sense: it alerted on so much of the corpus that landing inside an attack window was close to "
    "unavoidable. Recall and a false-positive rate must be read together, and a recall row from a "
    "saturated corpus supports no claim about detection at all."
)

_BASELINE_CAVEAT: Final = (
    "The behavioural model is fitted on a separate D1 normal corpus of the same plant, not on the "
    "attacked corpus. The calibrator is cross-fitted over two time folds, so every attack is "
    "scored in the fold whose calibration slice excluded it. A detection result is therefore a "
    "statement about Atlas given a well-fed baseline; a deployment fitted on four hours of a plant "
    "with a daily cycle would do worse, and that is a different measurement."
)

BREAKING_HARNESS_CAVEATS: Final = (
    _OUR_SIMULATION_CAVEAT,
    _FLAVOUR_CAVEAT,
    ATTACKS_ARE_OURS_CAVEAT,
    INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT,
    FINGERPRINT_CAVEAT,
    _UNCALIBRATED_CAVEAT,
    ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT,
    _BASELINE_CAVEAT,
    _SATURATION_CAVEAT,
)
"""Everything that must travel with any number this harness produces."""


class BreakingReport(BaseModel):
    """One regenerable answer to "how good is Atlas actually, and where does it break".

    Attributes:
        created_at: Wall-clock time of the run. Provenance, not a result.
        git_commit: Commit of the code that produced the numbers, when it could be determined.
        config: The settings, including the seed, so the run can be re-created.
        clean_map: Breaking points for attacks D2's own discipline covers. The headline.
        caveated_map: Breaking points for attacks carrying D2's documented residual. Never pooled
            with `clean_map`.
        breakdowns: The per-corpus detection results behind both maps.
        robustness: The input-hostile results, separately.
        command_results: What reading the control network did to the explanation ordering.
        caveats: `BREAKING_HARNESS_CAVEATS`, carried so the report stands alone.

    Invariants:
        No row appears in both maps: `clean_map` holds only `CLEAN` rows and `caveated_map` only
        `CAVEATED` ones, which `assemble` enforces by construction.
    """

    model_config = ConfigDict(frozen=True, ser_json_inf_nan="constants")

    created_at: UtcDatetime = Field(default_factory=utc_now)
    git_commit: str | None = None
    config: BreakingConfig
    clean_map: tuple[BreakingPoint, ...] = ()
    caveated_map: tuple[BreakingPoint, ...] = ()
    breakdowns: tuple[CorpusBreakdown, ...] = ()
    robustness: tuple[CorpusRobustness, ...] = ()
    command_results: tuple[CommandReasoningResult, ...] = ()
    caveats: tuple[str, ...] = BREAKING_HARNESS_CAVEATS

    @property
    def outcomes(self) -> tuple[AttackOutcome, ...]:
        """Every detection outcome across every corpus."""
        return tuple(outcome for breakdown in self.breakdowns for outcome in breakdown.outcomes)

    def dangerous_misses(self) -> tuple[AttackOutcome, ...]:
        """Attacks that drove the plant somewhere it does not go while Atlas stayed silent.

        The worst cell on the map, pulled out because it is the one a reader must not have to hunt
        for. Judged from D1's true-state record, not from the readings Atlas saw.
        """
        return tuple(
            outcome
            for outcome in self.outcomes
            if outcome.verdict is DetectionVerdict.MISSED_DANGEROUS
        )

    def saturated(self) -> tuple[CorpusBreakdown, ...]:
        """Corpora whose false-positive load makes their recall rows meaningless.

        Pulled out because a perfect recall bought with a hundred false alarms an hour reads, on the
        map alone, exactly like a detector that works. It is the most flattering way these numbers
        could be misread, so the report names it before it shows the map.
        """
        return tuple(
            breakdown
            for breakdown in self.breakdowns
            if breakdown.report.false_positive_rate > SATURATED_FP_PER_HOUR
        )

    def silent(self) -> tuple[CorpusBreakdown, ...]:
        """Corpora on which Atlas produced no subsystem events at all.

        Distinct from missing every attack: an engine that emitted nothing has not been outwitted
        attack by attack, it never spoke. That points at the baseline or the model's fit to the
        process rather than at the attacks' subtlety.
        """
        return tuple(breakdown for breakdown in self.breakdowns if breakdown.n_events == 0)

    def leaked_fingerprints(self) -> tuple[AttackOutcome, ...]:
        """Inert controls that nonetheless produced an alert.

        A manipulation of exactly zero magnitude that Atlas "detects" is not a detection: it is the
        generator leaking a tell. Should be empty; if it is not, nothing else in the report can be
        believed until it is explained.
        """
        return tuple(outcome for outcome in self.outcomes if outcome.is_inert and outcome.detected)


def assemble(
    breakdowns: Sequence[CorpusBreakdown],
    robustness: Sequence[CorpusRobustness],
    config: BreakingConfig,
) -> BreakingReport:
    """Build the report from what the harness measured, splitting the two maps apart.

    Args:
        breakdowns: Per-corpus detection results.
        robustness: Per-corpus input-hostile results. Never merged with the above.
        config: The settings the run used.

    Returns:
        The report, with the clean and caveated maps separated and the commit stamped.
    """
    outcomes = [outcome for breakdown in breakdowns for outcome in breakdown.outcomes]
    rows = breaking_points(outcomes)
    return BreakingReport(
        git_commit=current_git_commit(),
        config=config,
        clean_map=tuple(row for row in rows if row.fingerprint is FingerprintStatus.CLEAN),
        caveated_map=tuple(row for row in rows if row.fingerprint is FingerprintStatus.CAVEATED),
        breakdowns=tuple(breakdowns),
        robustness=tuple(robustness),
        command_results=tuple(
            result for breakdown in breakdowns for result in breakdown.command_results
        ),
    )


def _map_table(rows: Sequence[BreakingPoint]) -> str:
    """Render one breaking-point map as a table, boundary first."""
    if not rows:
        return "_No attacks of this kind were measured._\n"
    lines = [
        "| Plant | Type | Caught to | Missed from | Boundary | Caught | Missed | Danger | Inert |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        caught = f"{row.caught_hardest:.2f}" if row.caught_hardest is not None else "—"
        missed = f"{row.missed_easiest:.2f}" if row.missed_easiest is not None else "—"
        lines.append(
            f"| `{row.plant_id}` | `{row.attack_type.value}` | {caught} | {missed} | "
            f"{row.describe()} | {row.n_caught} | {row.n_missed} | {row.n_dangerous_misses} | "
            f"{row.detected_inert} |"
        )
    return "\n".join(lines) + "\n"


def _blind_spots(report: BreakingReport) -> str:
    """Render the plain written summary of where Atlas goes blind. The deliverable."""
    lines: list[str] = []

    for breakdown in report.silent():
        lines.append(
            f"**On `{breakdown.corpus}` Atlas emitted nothing at all** — zero subsystem events "
            f"across "
            f"{breakdown.report.normal_hours:.1f} normal hours and every attack in the battery. It "
            "did not lose to subtlety; it never spoke. Every row for this plant below is that one "
            "fact repeated, and the thing to investigate is the model's fit to this process, not "
            "the attacks."
        )
    for breakdown in report.saturated():
        lines.append(
            f"**Read no detection claim off `{breakdown.corpus}`.** It posts "
            f"{breakdown.report.false_positive_rate:.1f} false positives per normal hour "
            f"({breakdown.report.false_positives} over {breakdown.report.normal_hours:.1f} hours, "
            f"{breakdown.n_events} subsystem events). " + _SATURATION_CAVEAT
        )

    everywhere = [row for row in report.clean_map if row.blind_everywhere]
    if everywhere:
        lines.append(
            "**Whole attack types Atlas never saw, at any subtlety including the most blatant:** "
            + ", ".join(f"`{row.attack_type.value}` on `{row.plant_id}`" for row in everywhere)
            + ". Not boundaries but whole categories the engine is deaf to on that machine, and "
            "the first thing to fix."
        )
    boundaries = [
        row
        for row in report.clean_map
        if row.caught_hardest is not None and row.missed_easiest is not None
    ]
    if boundaries:
        lines.append("**Where the clean types break, per plant:**")
        for row in sorted(boundaries, key=lambda item: (item.plant_id, item.missed_easiest or 0.0)):
            lines.append(f"- `{row.plant_id}` / `{row.attack_type.value}` — {row.describe()}.")
    unlimited = [row for row in report.clean_map if row.caught_everywhere]
    if unlimited:
        saturated = {breakdown.plant_id for breakdown in report.saturated()}
        lines.append(
            "**Types the shipped battery never broke:** "
            + ", ".join(
                f"`{row.attack_type.value}` on `{row.plant_id}`"
                + (" *(saturated — see above)*" if row.plant_id in saturated else "")
                for row in unlimited
            )
            + ". The honest reading is 'not broken below the hardest subtlety tested', not 'always "
            "caught' — the dial would have to go further to find the limit. And where the row is "
            "marked saturated, it is not a detection result at all."
        )

    dangerous = report.dangerous_misses()
    if dangerous:
        lines.append(
            f"**{len(dangerous)} attack(s) drove the true state outside anything unattacked "
            "operation produced, while Atlas reported all-clear.** Judged from D1's true-state "
            "record, not from the telemetry, because for a falsified reading the telemetry is "
            "exactly what cannot be trusted:"
        )
        for outcome in dangerous:
            lines.append(
                f"- `{outcome.attack_id}` ({outcome.attack_type.value}, subtlety "
                f"{outcome.subtlety:.2f}) — true state left its envelope by "
                f"{outcome.true_state.peak_excess:.4f} on `{outcome.true_state.peak_signal}`."
            )

    leaked = report.leaked_fingerprints()
    if leaked:
        lines.append(
            f"**WARNING: {len(leaked)} zero-magnitude control(s) produced an alert.** A "
            "manipulation of exactly zero magnitude cannot be detected, so this is the generator "
            "leaking a tell. Nothing else in this report should be believed until it is explained: "
            + ", ".join(f"`{outcome.attack_id}`" for outcome in leaked)
        )
    else:
        lines.append(
            "**No zero-magnitude control produced an alert**, which is the anti-fingerprint check "
            "passing on the detection side: Atlas is not finding the injection itself."
        )
    return "\n\n".join(lines) + "\n"


def _commands_section(results: Sequence[CommandReasoningResult]) -> str:
    """Render what reading the control network did to the explanation ordering.

    Known-station and unknown-master windows are separate headlines. A pooled "led in n of m"
    would mix ADR 0014's remaining indistinguishability with ADR 0027's unknown-master split.
    """
    if not results:
        return (
            "_No command attacks were measured. On a plant declaring no control network this is by "
            "construction: no command attack can exist there, which is what makes it the control "
            "case for whether command visibility helps at all._\n"
        )
    lines = [
        "Known-station writes and unknown-master writes are **scored apart**. A write from a "
        "device already on the learned graph tests whether a new function on a known link can "
        "outrank maintenance (it cannot, by design: ADR 0014). A write from a device absent from "
        "that graph tests the unknown-master split (ADR 0027). Pooling the two lead rates would "
        "credit a template change the battery never exercised.",
        "",
    ]
    lines.extend(
        _issuer_kind_block(
            "Known-station issuers",
            tuple(item for item in results if item.issuer_kind is CommandIssuerKind.KNOWN_STATION),
            "Issuer already commanded someone in the baseline capture.",
        )
    )
    lines.extend(
        _issuer_kind_block(
            "Unknown-master issuers",
            tuple(item for item in results if item.issuer_kind is CommandIssuerKind.UNKNOWN_MASTER),
            "Issuer never commanded anyone in the baseline capture.",
        )
    )
    # The refusal is printed beside the counts rather than only in the caveat block, because
    # "moved in n of m" is the line most likely to be lifted out of this report on its own.
    lines += ["", f"> {ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT}"]
    return "\n".join(lines) + "\n"


def _issuer_kind_block(
    title: str, results: tuple[CommandReasoningResult, ...], why: str
) -> list[str]:
    """Render one issuer-kind subsection, including an explicit empty state."""
    lines = [f"### {title}", "", why, ""]
    if not results:
        lines.append("_None measured._")
        lines.append("")
        return lines
    moved = sum(1 for result in results if result.moved_toward_attack)
    leads = sum(1 for result in results if result.newly_leads)
    lines += [
        f"Of {len(results)} command attack(s), reading the control network moved "
        f"`{ATTACK_TEMPLATE_ID}` up the ordering in **{moved}** and made it the leading "
        f"explanation in **{leads}**.",
        "",
        "| Attack | Issuer | Subtlety | Rank on sensors | Rank with commands | Moved | "
        "Command evidence |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in results:
        before = result.sensor_only.rank
        after = result.with_commands.rank
        issuer = result.issuer or "—"
        lines.append(
            f"| `{result.attack_id}` | `{issuer}` | {result.subtlety:.2f} | "
            f"{before if before is not None else 'not raised'} | "
            f"{after if after is not None else 'not raised'} | "
            f"{'yes' if result.moved_toward_attack else 'no'} | {result.n_command_evidence} |"
        )
    lines.append("")
    return lines


def _robustness_section(results: Sequence[CorpusRobustness]) -> str:
    """Render the input-hostile results. Robustness, never detection."""
    if not results:
        return "_No input-hostile corpora were measured._\n"
    lines = [
        "| Corpus | Case | Kind | Verdict | Error | Baseline shift |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for corpus in results:
        for outcome in corpus.outcomes:
            shift = f"{outcome.baseline_shift:.4f}" if outcome.baseline_shift is not None else "—"
            kind = f"`{outcome.attack_type.value}`" if outcome.attack_type else "undeclared"
            lines.append(
                f"| `{corpus.corpus}` | `{outcome.attack_id}` | {kind} | "
                f"{outcome.verdict.value} | {outcome.error_type or '—'} | {shift} |"
            )
    crashed = [outcome for corpus in results for outcome in corpus.outcomes if not outcome.is_safe]
    lines.append("")
    if crashed:
        lines.append(
            f"**{len(crashed)} case(s) crashed** — a failure the code did not describe, which is a "
            "defect: " + ", ".join(f"`{outcome.attack_id}`" for outcome in crashed)
        )
    else:
        lines.append(
            "**No case crashed.** Every corruption was either refused loudly or consumed without "
            "error. A loud refusal is the correct behaviour, not a failure."
        )
    return "\n".join(lines) + "\n"


def render(report: BreakingReport) -> str:
    """Render the whole report as Markdown.

    Args:
        report: The assembled report.

    Returns:
        The document. Deterministic apart from ``created_at`` and the commit.
    """
    corpora = ", ".join(breakdown.corpus for breakdown in report.breakdowns) or "none"
    fp_rows = "\n".join(
        f"| `{breakdown.corpus}` | `{breakdown.fit_corpus}` | "
        f"{breakdown.report.normal_hours:.2f} | {breakdown.report.false_positives} | "
        f"{breakdown.report.false_positive_rate:.4f} | "
        f"{breakdown.n_events} | {breakdown.n_narratives} |"
        for breakdown in report.breakdowns
    )
    latency_rows = "\n".join(
        f"| `{breakdown.corpus}` | {breakdown.report.latency.count} | "
        f"{_seconds(breakdown.report.latency.min_seconds)} | "
        f"{_seconds(breakdown.report.latency.median_seconds)} | "
        f"{_seconds(breakdown.report.latency.max_seconds)} |"
        for breakdown in report.breakdowns
    )
    return f"""# Atlas — the breaking harness (PART D3)

**Run:** {report.created_at.isoformat()} · **Commit:** `{report.git_commit or "unknown"}` ·
**Seed:** {report.config.seed} · **Corpora:** {corpora}

> {_OUR_SIMULATION_CAVEAT}

---

## 1. Where Atlas goes blind

{_blind_spots(report)}

---

## 2. The breaking-point map — clean results

These are attacks whose mechanism D2's anti-fingerprint discipline covers, so a detection here is
evidence about Atlas. This is the headline map and the only part that supports the sentence *"Atlas
detects plant attacks down to this subtlety"*.

{_map_table(report.clean_map)}

## 3. The breaking-point map — fingerprint-caveated results

{FINGERPRINT_CAVEAT}

**These rows are not folded into the map above and must not be quoted beside it.**

{_map_table(report.caveated_map)}

---

## 4. False-positive load and detection latency

The denominator is hours of *normal* operation, so an attack-dense corpus cannot flatter the rate.
Every number here is `phos.eval`'s own.

| Corpus | Fitted on | Normal hours | False positives | FP / hour | Events | Narratives |
| --- | --- | --- | --- | --- | --- | --- |
{fp_rows}

| Corpus | Windows detected | Fastest (s) | Median (s) | Slowest (s) |
| --- | --- | --- | --- | --- |
{latency_rows}

{_BASELINE_CAVEAT}

---

## 5. Did reading the commands move the explanation?

{_commands_section(report.command_results)}

{_UNCALIBRATED_CAVEAT}

---

## 6. Input-hostile robustness — a separate claim

{INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT}

{_robustness_section(report.robustness)}

---

## 7. The boundary on all of it

{chr(10).join(f"{index}. {caveat}" for index, caveat in enumerate(report.caveats, start=1))}
"""


def _seconds(value: float | None) -> str:
    """Render an optional duration for a table cell."""
    return f"{value:.0f}" if value is not None else "—"


def write_report(
    report: BreakingReport,
    directory: Path = DEFAULT_REPORT_DIR,
    *,
    log: bool = True,
    stem: str = "breaking-report",
) -> tuple[Path, Path]:
    """Write the report and append its per-corpus harness reports to the experiment log.

    Args:
        report: The assembled report.
        directory: Where to write the Markdown and JSON.
        log: Whether to append to the experiment log. False writes the files and nothing else.
            Only detection ``breakdowns`` are appended; a hostile-only report has none.
        stem: Filename stem for the Markdown and JSON. The default ``breaking-report`` is the
            detection map. A hostile-only run must pass a different stem so it cannot overwrite
            those maps.

    Returns:
        The Markdown path and the JSON path.
    """
    directory.mkdir(parents=True, exist_ok=True)
    filename = Path(stem).name
    markdown = directory / f"{filename}.md"
    machine = directory / f"{filename}.json"
    markdown.write_text(render(report), encoding="utf-8")
    machine.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")

    if log:
        for breakdown in report.breakdowns:
            append_to_experiment_log(
                apply_saturation_policy(
                    breakdown.report.model_copy(update={"git_commit": report.git_commit}),
                    DEFAULT_SYNTH_SATURATION,
                )
            )
        logger.info("appended %d harness report(s) to the experiment log", len(report.breakdowns))

    logger.info("wrote the breaking report to %s and %s", markdown, machine)
    return markdown, machine


def summary_json(report: BreakingReport) -> str:
    """Return the maps and the blind spots as compact JSON, for a machine reading the result."""
    return json.dumps(
        {
            "commit": report.git_commit,
            "seed": report.config.seed,
            "clean": [
                {
                    "plant": row.plant_id,
                    "type": row.attack_type.value,
                    "caught_hardest": row.caught_hardest,
                    "missed_easiest": row.missed_easiest,
                    "monotone": row.monotone,
                    "boundary": row.describe(),
                }
                for row in report.clean_map
            ],
            "caveated": [
                {
                    "plant": row.plant_id,
                    "type": row.attack_type.value,
                    "caught_hardest": row.caught_hardest,
                    "missed_easiest": row.missed_easiest,
                    "boundary": row.describe(),
                }
                for row in report.caveated_map
            ],
            "saturated_corpora": [breakdown.corpus for breakdown in report.saturated()],
            "silent_corpora": [breakdown.corpus for breakdown in report.silent()],
            "dangerous_misses": [outcome.attack_id for outcome in report.dangerous_misses()],
            "leaked_fingerprints": [outcome.attack_id for outcome in report.leaked_fingerprints()],
        },
        indent=2,
        sort_keys=True,
    )
