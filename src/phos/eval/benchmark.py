"""PHOS Benchmark v1 — freeze the ruler before anyone tunes against it (ADR 0062).

This module is the measurement contract for Clock B. It **cites** already-published public rows
and **refuses** cells the files cannot support. It does not re-fit HAI, distillation, or CERT.
It does not retune Atlas templates. It does not pool known-station 0/16 with unknown-master 1/4.

A later model that wants to be compared to these rows must add a *new* detector name. Overwriting
``atlas-mahalanobis`` on HAI, the ungated distillation Mahalanobis row, or CERT 6B is forbidden.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from phos.eval.report import current_git_commit

__all__ = [
    "BENCHMARK_PROTOCOL_ID",
    "BENCHMARK_SEED",
    "CERT_PRECISION_POLICY_AT_48",
    "CERT_SIX_B_PRECISION_AT_48",
    "CERT_SIX_B_RECALL",
    "DISTILLATION_PERTURBATION_RECALL",
    "DISTILLATION_REDUCTION_VS_GAUSSIAN",
    "DISTILLATION_UNGATED_FP_PER_HOUR",
    "HAI_GAUSSIAN_FP_PER_HOUR",
    "HAI_GROUPED_FP_PER_HOUR",
    "HAI_GROUPED_PRECISION",
    "HAI_MAHALANOBIS_FP_PER_HOUR",
    "HAI_MAHALANOBIS_PRECISION",
    "HAI_PCA_FP_PER_HOUR",
    "HAI_WINDOW_RECALL",
    "KNOWN_STATION_LED",
    "KNOWN_STATION_MOVED",
    "KNOWN_STATION_N",
    "PUBLIC_COMMAND_CORPUS_PRESENT",
    "UNKNOWN_MASTER_LED",
    "UNKNOWN_MASTER_MOVED",
    "UNKNOWN_MASTER_N",
    "BenchmarkRow",
    "BenchmarkTable",
    "CellStatus",
    "RowFamily",
    "assemble_v1_table",
    "render_v1_json",
    "render_v1_markdown",
]

BENCHMARK_PROTOCOL_ID: Final = "phos-benchmark-v1"
BENCHMARK_SEED: Final = 11
"""HAI three-way public split seed (encyclopedia 11 / atlas-report). Not a search dimension."""

HAI_GAUSSIAN_FP_PER_HOUR: Final = 8389.81
HAI_PCA_FP_PER_HOUR: Final = 17529.93
HAI_MAHALANOBIS_FP_PER_HOUR: Final = 646.58
HAI_GROUPED_FP_PER_HOUR: Final = 53.26
HAI_WINDOW_RECALL: Final = 1.0
HAI_MAHALANOBIS_PRECISION: Final = 0.0047
HAI_GROUPED_PRECISION: Final = 0.0094

DISTILLATION_UNGATED_FP_PER_HOUR: Final = 18.72
DISTILLATION_PERTURBATION_RECALL: Final = 0.60
DISTILLATION_REDUCTION_VS_GAUSSIAN: Final = 8.6

CERT_SIX_B_PRECISION_AT_48: Final = 0.104
CERT_SIX_B_RECALL: Final = 0.5
CERT_PRECISION_POLICY_AT_48: Final = 0.083

KNOWN_STATION_LED: Final = 0
KNOWN_STATION_N: Final = 16
KNOWN_STATION_MOVED: Final = 6
UNKNOWN_MASTER_LED: Final = 1
UNKNOWN_MASTER_N: Final = 4
UNKNOWN_MASTER_MOVED: Final = 4
PUBLIC_COMMAND_CORPUS_PRESENT: Final = False

_PUBLIC_COMMAND_REFUSAL: Final = (
    "REFUSED (ADR 0040): discover_labelled_command_corpora is empty. Data4Cyber labels are "
    "1 Hz process phases, not command-action windows. This cell is not a lead rate."
)
_TRANSFER_REFUSAL: Final = (
    "REFUSED: HAI→BATADAL transfer is not a measurement until a declared shared plant-state "
    "schema exists. Different signal names are not a leave-one-plant protocol."
)
_BUDGET_REFUSAL: Final = (
    "REFUSED (ADR 0031): 2-3 actionable alerts/day on public distillation is uneearned. "
    "Phase-conditional is louder than ungated Mahalanobis. dwell_samples stays 1. "
    "Do not invent a phase column."
)
_PEER_REFUSAL: Final = (
    "REFUSED (ADR 0023): CERT r3.1 has zero peer-relative positives. Peer-group advantage "
    "stays retired. r4.2 is not a peer corpus."
)
_ATTRIBUTION_CAVEAT: Final = "ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT"
_PERTURBATION_CAVEAT: Final = "PERTURBATION_RECALL_IS_NOT_ATTACK_RECALL"
_PRECISION_LOSS_CAVEAT: Final = "MEASURED_LOSS_VS_6B"


class CellStatus(StrEnum):
    """How a table cell was produced."""

    CITED = "CITED"
    """Copied from a frozen public harness row. Not remeasured in this protocol."""

    REFUSED = "REFUSED"
    """The files cannot support the claim. Silence is the measurement."""

    DIAGNOSTIC = "DIAGNOSTIC"
    """Scored on attacks we wrote, with the standing attribution caveat. Not a field rate."""


class RowFamily(StrEnum):
    """Incomparable families. Do not smear a number from one family onto another."""

    ATLAS_PROCESS_CYBER = "atlas-process-cyber"
    ATLAS_PROCESS_PERTURBATION = "atlas-process-perturbation"
    ATLAS_COMMAND_PUBLIC = "atlas-command-public"
    ATLAS_COMMAND_D2 = "atlas-command-d2"
    SENTIEL = "sentiel"
    TRANSFER = "transfer"


class BenchmarkRow(BaseModel):
    """One cell of PHOS Benchmark v1."""

    model_config = ConfigDict(frozen=True)

    family: RowFamily
    dataset: str
    detector: str
    status: CellStatus
    window_recall: float | None = None
    fp_per_normal_hour: float | None = None
    fp_per_normal_day: float | None = None
    precision: float | None = None
    precision_at_budget: float | None = None
    unique_leads: int | None = None
    n: int | None = None
    caveat: str | None = None
    refusal_reason: str | None = None
    overwrites_public_log: bool = False
    citation: str = ""


class BenchmarkTable(BaseModel):
    """The frozen v1 table. Rows are addressed by (family, dataset, detector)."""

    model_config = ConfigDict(frozen=True)

    protocol: str = BENCHMARK_PROTOCOL_ID
    seed: int = BENCHMARK_SEED
    rows: tuple[BenchmarkRow, ...] = Field(min_length=1)

    def row(self, family: str, dataset: str, detector: str) -> BenchmarkRow:
        """Return the unique cell for ``(family, dataset, detector)``.

        Raises:
            KeyError: If no such cell exists. Callers must not invent transfer rows.
        """
        for item in self.rows:
            if (
                item.family.value == family
                and item.dataset == dataset
                and item.detector == detector
            ):
                return item
        raise KeyError((family, dataset, detector))


def _hour_to_day(fp_per_hour: float) -> float:
    return round(fp_per_hour * 24.0, 2)


def assemble_v1_table() -> BenchmarkTable:
    """Build the frozen v1 table from cited public numbers and named refusals."""
    rows = (
        BenchmarkRow(
            family=RowFamily.ATLAS_PROCESS_CYBER,
            dataset="hai",
            detector="model:gaussian",
            status=CellStatus.CITED,
            window_recall=HAI_WINDOW_RECALL,
            fp_per_normal_hour=HAI_GAUSSIAN_FP_PER_HOUR,
            fp_per_normal_day=_hour_to_day(HAI_GAUSSIAN_FP_PER_HOUR),
            precision=0.0043,
            citation="encyclopedia/11 HAI three-way seed 11; atlas-report",
        ),
        BenchmarkRow(
            family=RowFamily.ATLAS_PROCESS_CYBER,
            dataset="hai",
            detector="model:atlas-pca",
            status=CellStatus.CITED,
            window_recall=HAI_WINDOW_RECALL,
            fp_per_normal_hour=HAI_PCA_FP_PER_HOUR,
            fp_per_normal_day=_hour_to_day(HAI_PCA_FP_PER_HOUR),
            precision=0.0048,
            citation="encyclopedia/11: PCA residual lost; kept, not tuned away (ADR 0009)",
        ),
        BenchmarkRow(
            family=RowFamily.ATLAS_PROCESS_CYBER,
            dataset="hai",
            detector="atlas-mahalanobis",
            status=CellStatus.CITED,
            window_recall=HAI_WINDOW_RECALL,
            fp_per_normal_hour=HAI_MAHALANOBIS_FP_PER_HOUR,
            fp_per_normal_day=_hour_to_day(HAI_MAHALANOBIS_FP_PER_HOUR),
            precision=HAI_MAHALANOBIS_PRECISION,
            citation="encyclopedia/11 HAI Mahalanobis 646.58 FP/hour at recall 1.00",
        ),
        BenchmarkRow(
            family=RowFamily.ATLAS_PROCESS_CYBER,
            dataset="hai",
            detector="atlas-mahalanobis-grouped",
            status=CellStatus.CITED,
            window_recall=HAI_WINDOW_RECALL,
            fp_per_normal_hour=HAI_GROUPED_FP_PER_HOUR,
            fp_per_normal_day=_hour_to_day(HAI_GROUPED_FP_PER_HOUR),
            precision=HAI_GROUPED_PRECISION,
            caveat="COUNTING_CHANGE_NOT_A_CONTROL_ROOM",
            citation="ADR 0011: grouping shrinks the queue; 53.26/hour is not 2-3/day",
        ),
        BenchmarkRow(
            family=RowFamily.ATLAS_PROCESS_PERTURBATION,
            dataset="batch-distillation",
            detector="atlas-mahalanobis",
            status=CellStatus.CITED,
            window_recall=DISTILLATION_PERTURBATION_RECALL,
            fp_per_normal_hour=DISTILLATION_UNGATED_FP_PER_HOUR,
            fp_per_normal_day=_hour_to_day(DISTILLATION_UNGATED_FP_PER_HOUR),
            caveat=_PERTURBATION_CAVEAT,
            citation="ADR 0025/0031 ungated Mahalanobis 18.72; 8.6x vs Gaussian is not 10x",
        ),
        BenchmarkRow(
            family=RowFamily.ATLAS_PROCESS_PERTURBATION,
            dataset="batch-distillation",
            detector="2-3-per-day",
            status=CellStatus.REFUSED,
            refusal_reason=_BUDGET_REFUSAL,
            citation="ADR 0031",
        ),
        BenchmarkRow(
            family=RowFamily.ATLAS_COMMAND_PUBLIC,
            dataset="none",
            detector="command-lead",
            status=CellStatus.REFUSED,
            refusal_reason=_PUBLIC_COMMAND_REFUSAL,
            citation="ADR 0040",
        ),
        BenchmarkRow(
            family=RowFamily.ATLAS_COMMAND_D2,
            dataset="synth-water-power-graded",
            detector="known-station",
            status=CellStatus.DIAGNOSTIC,
            unique_leads=KNOWN_STATION_LED,
            n=KNOWN_STATION_N,
            caveat=_ATTRIBUTION_CAVEAT,
            citation="ADR 0038: unique lead 0/16; moved 6/16; must not pool",
        ),
        BenchmarkRow(
            family=RowFamily.ATLAS_COMMAND_D2,
            dataset="synth-water-unknown-master",
            detector="unknown-master",
            status=CellStatus.DIAGNOSTIC,
            unique_leads=UNKNOWN_MASTER_LED,
            n=UNKNOWN_MASTER_N,
            caveat=_ATTRIBUTION_CAVEAT,
            citation="ADR 0038: unique lead 1/4; D2 diagnostic; 1.1650 FP/hour saturated",
        ),
        BenchmarkRow(
            family=RowFamily.SENTIEL,
            dataset="cert-r3.1",
            detector="aggregate:gaussian:peer-set-6B",
            status=CellStatus.CITED,
            window_recall=CERT_SIX_B_RECALL,
            precision_at_budget=CERT_SIX_B_PRECISION_AT_48,
            n=48,
            citation="ADR 0032: 6B at 48 alerts, precision 0.104 (5 TP / 43 FP), recall 0.5",
        ),
        BenchmarkRow(
            family=RowFamily.SENTIEL,
            dataset="cert-r3.1",
            detector=":precision",
            status=CellStatus.CITED,
            window_recall=CERT_SIX_B_RECALL,
            precision_at_budget=CERT_PRECISION_POLICY_AT_48,
            n=48,
            caveat=_PRECISION_LOSS_CAVEAT,
            citation="ADR 0032: :precision 0.083 is a measured loss vs 6B; do not headline",
        ),
        BenchmarkRow(
            family=RowFamily.SENTIEL,
            dataset="cert-r3.1",
            detector="peer-advantage",
            status=CellStatus.REFUSED,
            refusal_reason=_PEER_REFUSAL,
            citation="ADR 0023",
        ),
        BenchmarkRow(
            family=RowFamily.TRANSFER,
            dataset="hai→batadal",
            detector="shared-schema",
            status=CellStatus.REFUSED,
            refusal_reason=_TRANSFER_REFUSAL,
            citation="ADR 0062 Clock B freeze",
        ),
    )
    return BenchmarkTable(rows=rows)


def render_v1_markdown(table: BenchmarkTable) -> str:
    """Render a deterministic Markdown table. No git sha — that lives in the JSON sidecar."""
    lines = [
        f"# {table.protocol}",
        "",
        "Frozen **before** Clock B model work (ADR 0062). Cited cells are copies of already-",
        "published public rows. REFUSED cells are measurements: the files cannot support the",
        "claim. Do not retune Atlas templates. Do not overwrite ungated HAI Mahalanobis",
        "**646.58**, distillation **18.72**, or CERT 6B **0.104**. Do not pool command issuers.",
        "Must not pool known-station **0/16** with unknown-master **1/4**. Cycle ≥70% remains",
        "unearned.",
        "",
        f"- Protocol: `{table.protocol}`",
        f"- Seed (HAI public split): `{table.seed}`",
        "- Threshold search on this split: **forbidden**",
        "",
        "| Family | Dataset | Detector | Status | Window recall | FP/normal hour | "
        "FP/normal day | Precision | Precision@budget | Unique lead | n | Caveat / refusal |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in table.rows:
        lines.append(_row_markdown(row))
    lines.extend(
        [
            "",
            "D2 known-station unique lead **0/16**. D2 unknown-master unique lead **1/4** "
            "(diagnostic, not a field rate). Public command row: REFUSED.",
            "",
        ]
    )
    return "\n".join(lines)


def _row_markdown(row: BenchmarkRow) -> str:
    """Render one table row. Split so ruff does not demand a 180-character f-string."""
    cells = (
        row.family.value,
        row.dataset,
        row.detector,
        row.status.value,
        _fmt(row.window_recall),
        _fmt(row.fp_per_normal_hour),
        _fmt(row.fp_per_normal_day),
        _fmt(row.precision),
        _fmt(row.precision_at_budget),
        _lead_cell(row),
        _fmt_int(row.n),
        _note(row),
    )
    return "| " + " | ".join(cells) + " |"


def render_v1_json(table: BenchmarkTable, *, git_commit: str | None = None) -> str:
    """Serialise the table plus optional git provenance. Never includes a threshold search."""
    commit = git_commit if git_commit is not None else current_git_commit()
    payload = {
        "protocol": table.protocol,
        "seed": table.seed,
        "git_commit": commit,
        "threshold_search": False,
        "public_command_corpus_present": PUBLIC_COMMAND_CORPUS_PRESENT,
        "rows": [item.model_dump(mode="json") for item in table.rows],
    }
    import json

    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _fmt(value: float | None) -> str:
    if value is None:
        return "—"
    if value == int(value) and abs(value) >= 1:
        return str(int(value)) if value == 1 else f"{value:.2f}".rstrip("0").rstrip(".")
    if abs(value) >= 10:
        return f"{value:.2f}"
    return f"{value:.4f}".rstrip("0").rstrip(".") if value < 1 else f"{value:.2f}"


def _fmt_int(value: int | None) -> str:
    return "—" if value is None else str(value)


def _lead_cell(row: BenchmarkRow) -> str:
    if row.unique_leads is None or row.n is None:
        return "—"
    return f"{row.unique_leads}/{row.n}"


def _note(row: BenchmarkRow) -> str:
    if row.status is CellStatus.REFUSED:
        return (row.refusal_reason or "REFUSED").replace("|", "/")
    parts = [part for part in (row.caveat, row.citation) if part]
    return " ".join(parts).replace("|", "/") if parts else "—"
