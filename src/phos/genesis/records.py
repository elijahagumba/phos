"""The GENESIS scientific record, as data rather than as prose.

Every guard in ``.claude/hooks/`` reads English. ``declared_before_harness.py`` says so in its
own docstring: "These records carry no machine-readable kind, so the guard cannot do better than
their own words." That is the reason the loop is slow. A regex over a title cannot be trusted to
refuse, so every guard ships advisory; because the guards only warn, the prohibitions have to be
carried in prose a session reads at the start; because the prose carries them, each record is
written long and by hand.

These three models give the record a machine-readable kind. A `Question` is what is being asked, a
`Experiment` is a declaration that may later carry its measurement, and a `Finding` is a claim at a
level on the discovery ladder. The prose ADR is then rendered from the record instead of being the
record, and a guard can answer "is this command declared?" exactly.

The models are frozen: a measurement is added by producing a new record, never by mutating the one
that was committed before the run. That is what keeps section VIII's "never silently alter
historical experimental results" a property of the store rather than a promise in a charter.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Phases of an experiment record. ``declared`` predates its run; ``measured`` carries numbers;
#: ``judged`` carries the verdict computed from those numbers against the declared bars.
Phase = Literal["declared", "measured", "judged"]

#: Which data tier the corpus sits in (``docs/rules/data-tiers.md``). ``never`` is refused at
#: declaration time: a record cannot declare a run on a corpus the rules forbid reading.
Tier = Literal["iterate", "once", "never"]

#: The comparators a bar may use. A bar is a threshold a number either clears or does not, so
#: there is no "improves" and no "approximately".
Comparator = Literal[">=", ">", "<=", "<", "==", "!="]

#: Status of a research question.
QuestionStatus = Literal["open", "investigating", "answered", "abandoned"]

#: Identifier shapes. The prefix says which kind of record it is without opening the file.
_QUESTION_ID: Final = re.compile(r"^Q-\d{4}$")
_EXPERIMENT_ID: Final = re.compile(r"^E-\d{4}$")
_FINDING_ID: Final = re.compile(r"^F-\d{4}$")

#: The nine criteria of charter section XII. Each is scored 1--5. They are kept as separate fields
#: rather than a single number so that a ranking can be argued with, and so that "cheapest first"
#: is visible as a choice instead of hiding inside one score. ``Priority`` is checked against this
#: tuple by ``tests/genesis/test_records.py``, so the list and the model cannot drift apart.
PRIORITY_CRITERIA: Final[tuple[str, ...]] = (
    "significance",
    "originality",
    "feasibility",
    "information_gain",
    "tractability",
    "relevance",
    "operational_impact",
    "evidence",
    "cost",
)


class Priority(BaseModel):
    """Charter section XII scoring for one research question.

    Each criterion is 1--5. ``cost`` is scored as cost, so a cheap question scores 1 and an
    expensive one scores 5; ``rank`` subtracts it rather than adding it.

    Attributes:
        significance: Potential scientific significance.
        originality: How far the question goes beyond what is already published.
        feasibility: Whether it can be attempted with the data and compute that exist.
        information_gain: How much the answer would change what PHOS does next.
        tractability: Whether an experiment can settle it rather than merely illuminate it.
        relevance: Relevance to Atlas.
        operational_impact: Potential effect on a real plant's queue.
        evidence: How much supporting evidence already exists.
        cost: Cost of investigation, 1 cheap to 5 expensive.
    """

    model_config = ConfigDict(frozen=True)

    significance: int = Field(ge=1, le=5)
    originality: int = Field(ge=1, le=5)
    feasibility: int = Field(ge=1, le=5)
    information_gain: int = Field(ge=1, le=5)
    tractability: int = Field(ge=1, le=5)
    relevance: int = Field(ge=1, le=5)
    operational_impact: int = Field(ge=1, le=5)
    evidence: int = Field(ge=1, le=5)
    cost: int = Field(ge=1, le=5)

    def rank(self) -> int:
        """Return the ordering score: every criterion but cost, less cost.

        The charter forbids automatically preferring the easiest experiment, so cost is one term
        among nine and cannot dominate. A high-cost question with high significance still ranks
        above a cheap one with none.

        Returns:
            The sum of the eight value criteria minus ``cost``.
        """
        value = (
            self.significance
            + self.originality
            + self.feasibility
            + self.information_gain
            + self.tractability
            + self.relevance
            + self.operational_impact
            + self.evidence
        )
        return value - self.cost


class Question(BaseModel):
    """One research question, with the gap it addresses and why it is worth asking.

    Attributes:
        id: ``Q-NNNN``.
        title: The question as a sentence.
        frontier: Which charter section V frontier it belongs to, or ``"discovered"`` for one
            GENESIS found itself.
        status: Where the question stands.
        opened: The date it was registered.
        state_of_the_art: What is already established, named concretely.
        gap: The precise unresolved part. Charter section II step 3.
        priority: Section XII scoring.
        experiments: Experiment ids attempted against it.
        refs: Records, papers or paths that back the gap statement.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=_QUESTION_ID.pattern)
    title: str = Field(min_length=10)
    frontier: str
    status: QuestionStatus = "open"
    opened: date
    state_of_the_art: str = Field(min_length=10)
    gap: str = Field(min_length=10)
    priority: Priority
    experiments: tuple[str, ...] = ()
    refs: tuple[str, ...] = ()


class Bar(BaseModel):
    """One threshold, declared before the run, that a measured number either clears or does not.

    Attributes:
        id: Short key, unique within the experiment, used to attach the measured value.
        metric: What is measured, named as the harness names it.
        comparator: How the value is compared with the threshold.
        threshold: The declared number.
        text: The bar in words, for the rendered ADR. It must not contradict the comparison.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1, max_length=32)
    metric: str = Field(min_length=1)
    comparator: Comparator
    threshold: float
    text: str = Field(min_length=1)

    def met_by(self, value: float) -> bool:
        """Return whether ``value`` clears this bar.

        Args:
            value: The measured number for ``metric``.

        Returns:
            True when the declared comparison holds.
        """
        match self.comparator:
            case ">=":
                return value >= self.threshold
            case ">":
                return value > self.threshold
            case "<=":
                return value <= self.threshold
            case "<":
                return value < self.threshold
            case "==":
                return value == self.threshold
            case "!=":
                return value != self.threshold


class Declaration(BaseModel):
    """What was committed before anything ran.

    Attributes:
        date: The date of the declaration.
        hypothesis: The falsifiable claim. Charter section II step 4.
        why_it_might_be_wrong: Charter section II step 5. A declaration without this is refused.
        falsifier: The observation that would disprove the hypothesis. Section II step 6.
        baseline: What the method is measured against. Section II step 7.
        command: The exact command the run will use. A guard compares against this string.
        corpus: The dataset name as ``docs/rules/data-tiers.md`` names it.
        tier: That corpus's tier.
        result_name: The name the result will be recorded under.
        challenger_sha256: Digest of the implementation under test, where the lane computes one.
        bars: The thresholds. At least one, and each clears or does not.
    """

    model_config = ConfigDict(frozen=True)

    date: date
    hypothesis: str = Field(min_length=10)
    why_it_might_be_wrong: str = Field(min_length=10)
    falsifier: str = Field(min_length=10)
    baseline: str = Field(min_length=3)
    command: str = Field(min_length=3)
    corpus: str = Field(min_length=1)
    tier: Tier
    result_name: str = Field(min_length=1)
    challenger_sha256: str | None = None
    bars: tuple[Bar, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _bar_ids_are_unique(self) -> Declaration:
        """Refuse two bars with the same id, which would make a value ambiguous."""
        ids = [bar.id for bar in self.bars]
        if len(set(ids)) != len(ids):
            raise ValueError("bar ids must be unique within a declaration")
        return self

    @model_validator(mode="after")
    def _never_tier_is_not_declarable(self) -> Declaration:
        """Refuse a declaration on a corpus the data-tier rule forbids reading."""
        if self.tier == "never":
            raise ValueError(
                f"corpus {self.corpus!r} is tier 'never' (docs/rules/data-tiers.md): "
                "a run on it cannot be declared"
            )
        return self


class Measurement(BaseModel):
    """The numbers the declared command produced.

    Attributes:
        date: When the run happened.
        commit: The commit the run was made from.
        report: Path to the harness report the numbers came from.
        values: Measured value per bar id. Every declared bar must appear.
        failures: Failure cases and unexpected results. Charter section IV requires them
            recorded, so an empty string is not accepted.
        notes: Anything else worth keeping, including compute cost.
    """

    model_config = ConfigDict(frozen=True)

    date: date
    commit: str = Field(min_length=7)
    report: str = Field(min_length=1)
    values: dict[str, float]
    failures: str = Field(min_length=1)
    notes: str = ""


class Verdict(BaseModel):
    """The judgement, computed from the measurement against the declared bars.

    ``outcome`` is derived, never typed in: ``kept`` when every bar is met, ``refused`` when any
    is missed. A refusal is a result (charter section VIII), so it is recorded the same way a
    kept result is.

    Attributes:
        outcome: ``kept`` or ``refused``.
        per_bar: Whether each declared bar was met, by bar id.
        adr: The rendered prose record, once it exists.
    """

    model_config = ConfigDict(frozen=True)

    outcome: Literal["kept", "refused"]
    per_bar: dict[str, bool]
    adr: str | None = None


class Experiment(BaseModel):
    """A declaration that may later carry its measurement and its verdict.

    One file holds all three phases so that the declaration cannot drift from the thing that was
    scored, and so that a guard reads one path to answer whether a command was declared.

    Attributes:
        id: ``E-NNNN``.
        question: The ``Q-NNNN`` this experiment serves.
        phase: Which phases the record carries.
        declared: Always present.
        measured: Present from phase ``measured``.
        verdict: Present from phase ``judged``.
        declaring_commit: The commit that put the declaration in history. A run with no value
            here has nothing predating it.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=_EXPERIMENT_ID.pattern)
    question: str = Field(pattern=_QUESTION_ID.pattern)
    phase: Phase
    declared: Declaration
    measured: Measurement | None = None
    verdict: Verdict | None = None
    declaring_commit: str | None = None

    @model_validator(mode="after")
    def _phase_matches_contents(self) -> Experiment:
        """Refuse a phase that claims more than the record carries."""
        if self.phase in ("measured", "judged") and self.measured is None:
            raise ValueError(f"phase {self.phase!r} with no measurement")
        if self.phase == "judged" and self.verdict is None:
            raise ValueError("phase 'judged' with no verdict")
        if self.phase == "declared" and self.measured is not None:
            raise ValueError("phase 'declared' with a measurement already attached")
        return self

    @model_validator(mode="after")
    def _every_bar_has_a_value(self) -> Experiment:
        """Refuse a measurement that leaves a declared bar unanswered or invents a new one."""
        if self.measured is None:
            return self
        declared = {bar.id for bar in self.declared.bars}
        measured = set(self.measured.values)
        if missing := sorted(declared - measured):
            raise ValueError(f"no measured value for declared bar(s): {', '.join(missing)}")
        if extra := sorted(measured - declared):
            raise ValueError(f"measured value for undeclared bar(s): {', '.join(extra)}")
        return self

    def compute_verdict(self) -> Verdict:
        """Return the verdict the measurement implies.

        Returns:
            A verdict whose ``outcome`` is ``kept`` only when every declared bar is met.

        Raises:
            ValueError: If the record carries no measurement.
        """
        if self.measured is None:
            raise ValueError(f"{self.id} has no measurement to judge")
        per_bar = {bar.id: bar.met_by(self.measured.values[bar.id]) for bar in self.declared.bars}
        outcome: Literal["kept", "refused"] = "kept" if all(per_bar.values()) else "refused"
        return Verdict(outcome=outcome, per_bar=per_bar)


class Review(BaseModel):
    """An independent attempt to falsify a finding. Charter section VII and section IX level 5.

    Attributes:
        date: When the review was made.
        reviewer: The role or person who made it, named.
        attempted: What was tried in order to break the claim.
        survived: Whether the claim survived. A review that agrees without attempting anything
            is not evidence (charter section VII), so ``attempted`` is required either way.
    """

    model_config = ConfigDict(frozen=True)

    date: date
    reviewer: str = Field(min_length=2)
    attempted: str = Field(min_length=10)
    survived: bool


class Finding(BaseModel):
    """A claim at a level on the charter section IX discovery ladder.

    Attributes:
        id: ``F-NNNN``.
        level: 0--5. ``levels.promotable`` decides whether the evidence supports it.
        claim: What is being asserted.
        evidence: Experiment ids that support it.
        prior_work: Named prior art the claim is positioned against. Required from level 1.
        improvement: What improved and by how much, with the baseline's number and the
            challenger's. Required from level 2, where the claim is that an existing method was
            measurably beaten. A machine can check that the numbers are on the record; whether
            they are the right ones is what the independent review is for.
        corpora: Distinct corpora the claim holds on. Required at level 4 and above.
        reviews: Independent falsification attempts. Required at level 5.
        reproduction: How to reproduce it. Required at level 5.
        limitations: What the claim does not cover. Never empty above level 0.
        history: Every level this finding has held, with the reason it moved.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=_FINDING_ID.pattern)
    level: int = Field(ge=0, le=5)
    claim: str = Field(min_length=10)
    evidence: tuple[str, ...] = ()
    prior_work: tuple[str, ...] = ()
    improvement: str = ""
    corpora: tuple[str, ...] = ()
    reviews: tuple[Review, ...] = ()
    reproduction: str = ""
    limitations: str = ""
    history: tuple[str, ...] = ()
