"""What PHOS decided, what became known afterwards, and a ledger that cannot be quietly rewritten.

Stage S1 of `docs/learning-engine.md` (ADR 0118). A detector's decision is stored the moment it is
made, as a `DecisionRecord`. Whatever is learned later (a corpus label, the synthetic plant's true
state, a work order, an operator's word) arrives as an `OutcomeRecord` that points at it. The two
are never merged and neither is ever edited: a correction is a new outcome that ``supersedes`` an
older one, and the history stays readable.

Both live in one append-only file, one JSON object per line, each line carrying the sha256 of the
line before it. `LearningLedger.load` re-walks the chain and refuses a file in which any line was
edited, removed or reordered. Because decisions and outcomes share the chain, an outcome can only
ever be appended after the decision it is about.

**Unknown stays unknown.** An outcome must name its ``kind``; ``unknown`` is a kind, and it is
neither a hit nor a false alarm. **An operator's word alone is not ground truth**: an outcome whose
source is ``operator`` cannot be ``confirmed`` without an independent corroborating reference.

Nothing here scores a detector, writes ``eval_runs/log.jsonl`` or changes a frozen row.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.ontology import Evidence, Hypothesis, Narrative
from phos.ontology.ids import UtcDatetime, new_id, utc_now

__all__ = [
    "GENESIS_HASH",
    "AlertRow",
    "Channel",
    "DecisionRecord",
    "LearningLedger",
    "LearningRecord",
    "LedgerError",
    "OutcomeKind",
    "OutcomeRecord",
    "OutcomeSource",
    "OutcomeStatus",
    "arena_eligibility",
    "sha256_text",
    "window_sha256",
]

DECISION_PREFIX: Final = "dec"
OUTCOME_PREFIX: Final = "out"

#: The ``prev`` of the first line: no line came before it.
GENESIS_HASH: Final = "0" * 64

OutcomeKind = Literal["attack", "maintenance", "fault", "benign", "unknown"]
OutcomeStatus = Literal["unresolved", "provisional", "confirmed", "disputed", "retracted"]
OutcomeSource = Literal[
    "corpus_label",
    "synthetic_truth",
    "work_order",
    "operator",
    "investigation",
    "partner_report",
]

#: The brief's five channels: A missed, B false positive, C explanation, D operator, E success.
Channel = Literal["missed", "false_positive", "explanation", "operator_feedback", "success"]

_EntryKind = Literal["decision", "outcome"]


class LedgerError(ValueError):
    """Raised when a ledger file is not an unbroken chain, or an append would break a rule."""


def sha256_text(text: str) -> str:
    """Return the hex sha256 of ``text`` encoded as UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class AlertRow(BaseModel):
    """One alert as the operator was shown it.

    Attributes:
        rank: Position in the queue, 1 first.
        time: When the alert fired, UTC.
        score: The detector's score; higher is more alarming.
        entities: What it was raised on.
    """

    model_config = ConfigDict(frozen=True)

    rank: int = Field(ge=1)
    time: UtcDatetime
    score: float
    entities: tuple[str, ...] = Field(min_length=1)


class DecisionRecord(BaseModel):
    """What a detector knew and said, stored at the time and never edited.

    Attributes:
        id: ``dec_`` identifier.
        decided_at: When the decision was made (run time, or replay time on a corpus).
        detector: The result name, e.g. ``atlas-v1-consistency``.
        commit: The git commit of the code that decided, when known.
        config_sha256: sha256 of the detector's configuration as serialised.
        fit: What the model was fitted on, in words (corpus, or seeds).
        fit_sha256: sha256 of that fitting input.
        source: The corpus or site the decision was about.
        source_role: Its ADR 0117 role at decision time, or ``None``.
        window_start: First instant of the input scored, UTC.
        window_end: Last instant of the input scored, UTC.
        input_sha256: sha256 of that input.
        budget_per_shift: Alerts per 8-hour shift in force.
        alerts: Every alert raised, in queue order.
        narratives: The narratives as emitted.
        hypotheses: The hypotheses as emitted.
        evidence: The evidence as emitted.
        calibrator: Which calibrator produced any confidence shown, or ``None``.

    Invariants:
        ``window_start <= window_end``; alert ranks are 1, 2, 3, ... in order; every id a
        narrative or hypothesis cites is present in the record.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: new_id(DECISION_PREFIX))
    decided_at: UtcDatetime = Field(default_factory=utc_now)
    detector: str = Field(min_length=1)
    commit: str | None = None
    config_sha256: str = Field(min_length=64, max_length=64)
    fit: str = Field(min_length=1)
    fit_sha256: str = Field(min_length=64, max_length=64)
    source: str = Field(min_length=1)
    source_role: str | None = None
    window_start: UtcDatetime
    window_end: UtcDatetime
    input_sha256: str = Field(min_length=64, max_length=64)
    budget_per_shift: int = Field(ge=1)
    alerts: tuple[AlertRow, ...] = ()
    narratives: tuple[Narrative, ...] = ()
    hypotheses: tuple[Hypothesis, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    calibrator: str | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.window_start > self.window_end:
            raise ValueError(f"window is inverted: {self.window_start} > {self.window_end}")
        ranks = [alert.rank for alert in self.alerts]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError(f"alert ranks must be 1..n in order, got {ranks}")
        evidence_ids = {item.id for item in self.evidence}
        hypothesis_ids = {item.id for item in self.hypotheses}
        for hypothesis in self.hypotheses:
            missing = set(hypothesis.supporting) | set(hypothesis.contradictory)
            if missing - evidence_ids:
                raise ValueError(f"{hypothesis.id} cites evidence not in the record")
        for narrative in self.narratives:
            if set(narrative.evidence_ids) - evidence_ids:
                raise ValueError(f"{narrative.id} cites evidence not in the record")
            if set(narrative.hypothesis_ids) - hypothesis_ids:
                raise ValueError(f"{narrative.id} cites a hypothesis not in the record")
        return self


class OutcomeRecord(BaseModel):
    """What became known after a decision, with how sure it is and where it came from.

    Attributes:
        id: ``out_`` identifier.
        decision_id: The decision it is about, or ``None`` for a miss nothing alerted on.
        window_start: Start of the time it is about, when ``decision_id`` is ``None``.
        window_end: End of that time.
        entities: What it is about.
        kind: What happened. ``unknown`` is a kind, never a default.
        status: How settled it is.
        source: Where it came from.
        source_ref: The label file, truth file, work-order id or note it rests on.
        occurred_at: When it happened.
        known_at: When PHOS learned it. Must not precede ``occurred_at``.
        supersedes: The outcome this one corrects, or ``None``.
        corroboration: Independent references that agree with it.

    Invariants:
        It is about a decision or a window, not neither. An ``operator`` outcome is not
        ``confirmed`` without corroboration.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: new_id(OUTCOME_PREFIX))
    decision_id: str | None = None
    window_start: UtcDatetime | None = None
    window_end: UtcDatetime | None = None
    entities: tuple[str, ...] = ()
    kind: OutcomeKind
    status: OutcomeStatus
    source: OutcomeSource
    source_ref: str = Field(min_length=1)
    occurred_at: UtcDatetime
    known_at: UtcDatetime
    supersedes: str | None = None
    corroboration: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _check(self) -> Self:
        start, end = self.window_start, self.window_end
        if (start is None) != (end is None):
            raise ValueError("an outcome window needs both a start and an end")
        if self.decision_id is None and start is None:
            raise ValueError("an outcome is about a decision or a window")
        if start is not None and end is not None and start > end:
            raise ValueError("outcome window is inverted")
        if self.known_at < self.occurred_at:
            raise ValueError("known_at precedes occurred_at")
        if self.source == "operator" and self.status == "confirmed" and not self.corroboration:
            raise ValueError("an operator's word alone cannot confirm an outcome")
        return self


class _Entry(BaseModel):
    model_config = ConfigDict(frozen=True)

    prev: str
    kind: _EntryKind
    record: DecisionRecord | OutcomeRecord


class LearningLedger:
    """The append-only, hash-chained file of decisions and outcomes.

    There is no update and no delete. `append_decision` and `append_outcome` are the only writes,
    and each checks its rules against everything already on file before writing a line.
    """

    def __init__(self, path: Path) -> None:
        """Open the ledger at ``path``, verifying the whole chain if the file exists.

        Raises:
            LedgerError: If an existing file is not an unbroken chain.
        """
        self._path = path
        self._decisions: dict[str, DecisionRecord] = {}
        self._outcomes: dict[str, OutcomeRecord] = {}
        self._order: list[str] = []
        self._head = GENESIS_HASH
        if path.is_file():
            self._replay(path.read_text(encoding="utf-8"))

    @property
    def head(self) -> str:
        """The sha256 of the last line, or `GENESIS_HASH` for an empty ledger."""
        return self._head

    def decisions(self) -> tuple[DecisionRecord, ...]:
        """Every decision, in the order appended."""
        return tuple(self._decisions[i] for i in self._order if i in self._decisions)

    def outcomes(self) -> tuple[OutcomeRecord, ...]:
        """Every outcome, in the order appended, superseded ones included."""
        return tuple(self._outcomes[i] for i in self._order if i in self._outcomes)

    def decision(self, decision_id: str) -> DecisionRecord:
        """Return the decision ``decision_id``.

        Raises:
            LedgerError: If there is none.
        """
        try:
            return self._decisions[decision_id]
        except KeyError:
            raise LedgerError(f"no decision {decision_id!r}") from None

    def current_outcomes(self, decision_id: str | None = None) -> tuple[OutcomeRecord, ...]:
        """Outcomes no later outcome supersedes, optionally only those about one decision."""
        superseded = {o.supersedes for o in self._outcomes.values() if o.supersedes is not None}
        return tuple(
            outcome
            for outcome in self.outcomes()
            if outcome.id not in superseded
            and (decision_id is None or outcome.decision_id == decision_id)
        )

    def append_decision(self, record: DecisionRecord) -> None:
        """Append a decision.

        Raises:
            LedgerError: If its id is already on file.
        """
        if record.id in self._decisions or record.id in self._outcomes:
            raise LedgerError(f"{record.id} is already on file")
        self._write("decision", record)

    def append_outcome(self, record: OutcomeRecord) -> None:
        """Append an outcome.

        Raises:
            LedgerError: If its id is on file; its decision is not on file; it was known before
                that decision was made; or what it supersedes is not on file, already
                superseded, or about something else.
        """
        self._check_outcome(record)
        self._write("outcome", record)

    def _check_outcome(self, record: OutcomeRecord) -> None:
        if record.id in self._decisions or record.id in self._outcomes:
            raise LedgerError(f"{record.id} is already on file")
        if record.decision_id is not None:
            decision = self.decision(record.decision_id)
            if record.known_at < decision.decided_at:
                raise LedgerError(f"{record.id} was known before {decision.id} was decided")
        if record.supersedes is not None:
            older = self._outcomes.get(record.supersedes)
            if older is None:
                raise LedgerError(f"{record.id} supersedes {record.supersedes!r}, not on file")
            if older.id not in {o.id for o in self.current_outcomes()}:
                raise LedgerError(f"{older.id} is already superseded")
            if (older.decision_id, older.window_start, older.window_end) != (
                record.decision_id,
                record.window_start,
                record.window_end,
            ):
                raise LedgerError(f"{record.id} is not about what {older.id} is about")

    def _write(self, kind: _EntryKind, record: DecisionRecord | OutcomeRecord) -> None:
        line = _Entry(prev=self._head, kind=kind, record=record).model_dump_json()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        self._accept(record, line)

    def _accept(self, record: DecisionRecord | OutcomeRecord, line: str) -> None:
        if isinstance(record, DecisionRecord):
            self._decisions[record.id] = record
        else:
            self._outcomes[record.id] = record
        self._order.append(record.id)
        self._head = sha256_text(line)

    def _replay(self, text: str) -> None:
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        for number, line in enumerate(lines, start=1):
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as error:
                raise LedgerError(f"line {number} is not JSON: {error}") from None
            if not isinstance(raw, dict) or raw.get("prev") != self._head:
                raise LedgerError(f"line {number} does not follow line {number - 1}")
            kind, body = raw.get("kind"), raw.get("record")
            record: DecisionRecord | OutcomeRecord
            try:
                if kind == "decision":
                    record = DecisionRecord.model_validate(body)
                    if record.id in self._decisions or record.id in self._outcomes:
                        raise LedgerError(f"{record.id} is already on file")
                elif kind == "outcome":
                    record = OutcomeRecord.model_validate(body)
                    self._check_outcome(record)
                else:
                    raise LedgerError(f"unknown kind {kind!r}")
            except (LedgerError, ValueError) as error:
                raise LedgerError(f"line {number}: {error}") from None
            self._accept(record, line)


def window_sha256(timestamps: Sequence[datetime], values: Sequence[Sequence[float]]) -> str:
    """Return a sha256 of a scored input: its timestamps and values, in order, as JSON.

    Raises:
        ValueError: If there are not as many value rows as timestamps.
    """
    rows = [
        [stamp.isoformat(), [float(value) for value in row]]
        for stamp, row in zip(timestamps, values, strict=True)
    ]
    return sha256_text(json.dumps(rows, separators=(",", ":")))


class LearningRecord(BaseModel):
    """A decision joined to what became known about it, and what may be learned from it.

    Derived: recomputable from the ledger and the diagnosis that produced it, so it is a cache and
    never a source of truth.

    Attributes:
        decision_id: The decision.
        outcome_ids: The current outcomes it was joined to.
        channel: Which of the five channels it belongs to.
        mechanism: The diagnosis's verdict, in that diagnosis's own vocabulary.
        quantities: The numbers the verdict read, so it can be checked.
        eligible: Whether the case may enter the arena (`arena_eligibility`).
        reason: Why, or why not.
    """

    model_config = ConfigDict(frozen=True)

    decision_id: str
    outcome_ids: tuple[str, ...]
    channel: Channel
    mechanism: str = Field(min_length=1)
    quantities: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    eligible: bool
    reason: str = Field(min_length=1)


def arena_eligibility(decision: DecisionRecord, outcome: OutcomeRecord | None) -> tuple[bool, str]:
    """Return whether a case may enter the arena, and why (ADR 0117 §2, ADR 0119).

    Only a ``confirmed`` outcome on a ``development`` source qualifies. A ``validation`` case
    reaches the gate as a count per mechanism; handing it to an agent with its labels and times
    would demote its corpus, which is a registry change this function never makes.
    """
    if outcome is None:
        return False, "no outcome is known"
    if outcome.status != "confirmed":
        return False, f"the outcome is {outcome.status}, not confirmed"
    role = decision.source_role
    if role == "development":
        return True, "a confirmed outcome on development data"
    if role == "validation":
        return False, (
            "a validation source: only counts per mechanism reach the gate; handing the case to "
            "an agent would demote the corpus to development (ADR 0117)"
        )
    if role == "held-out":
        return False, "a held-out source is never learned from before its single score"
    return False, "the source has no data role"
