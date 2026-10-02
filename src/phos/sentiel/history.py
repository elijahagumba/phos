"""What this user's own recent past looked like — the mechanism behind every enriched feature.

A raw daily count says what someone did. It does not say whether that is *normal for them*. Forty
logons is unremarkable for a night-shift administrator and extraordinary for a salesperson, and a
model fed only the count cannot tell those apart until it has learned a separate baseline for every
person — which is exactly what the per-``(entity, feature)`` models in `phos.models` do, once, over
a fixed training window, and then never revise. This module is the other half: a **causal, rolling**
summary of each user's own trailing behaviour, maintained as the corpus streams past, so that
`phos.sentiel.featurise` can emit "six standard deviations above their own norm" as a feature in its
own right rather than leaving the model to infer it.

Three guarantees hold, and the tests are written to break an implementation that loses any of them:

- **Causality.** A summary read for window *t* reflects only windows strictly before *t*. Reads
  never mutate; `TrailingHistory.observe` is the only thing that advances state, and the featuriser
  calls it *after* it has emitted the window. A baseline that included the window it judges would
  flatter every spike into ordinariness — the current value would drag the mean toward itself — and
  nothing downstream could detect that it had happened.
- **Boundedness.** Everything is a rolling window over the last `HistoryPolicy.trailing_windows`
  *populated* windows, so a user who changes role stops being judged against a year-old self, and
  memory does not grow with the length of the corpus. "Populated" matters: the featuriser emits
  nothing for a day a user was idle, so the history indexes activity, not the calendar.
- **Finiteness.** No read returns ``NaN`` or an infinity. A user who has never varied has a
  trailing standard deviation of zero, and dividing by it is the obvious way to put an infinity
  into an `Observation`; `HistoryPolicy.deviation_cap` is the documented answer instead.

Everything here is per user. Nothing in this module reads one user to answer a question about
another — that is peer-group baselining, it is PART 6B, and keeping it out of this layer is what
makes the boundary between the two testable.
"""

import math
from collections import Counter, deque
from collections.abc import Collection, Mapping
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "NEUTRAL_VALUE",
    "HistoryPolicy",
    "TrailingHistory",
]

NEUTRAL_VALUE: Final = 0.0
"""What every read returns when there is not yet enough history to answer honestly.

Zero, and named rather than written as a bare literal, because zero is the value that *claims
nothing*: a deviation of zero says "no departure from normal", a difference of zero says "no
change", a new-counterparty count of zero says "nobody new". When the history cannot support a
claim, claiming nothing is the correct answer, and any other sentinel — ``-1``, ``NaN``, a large
magic number — would be read by a downstream model as evidence of something. This is the cold-start
policy in one constant: the value is documented and deliberate, not a silent zero that happens to
fall out of an empty accumulator.

The cost is that a model cannot distinguish "no history" from "perfectly ordinary", and PART 6A
records that rather than hiding it: a user in their first `HistoryPolicy.min_history_windows`
active windows is invisible to every baseline-relative feature.
"""


class HistoryPolicy(BaseModel):
    """How far back a user's own history reaches, and what it takes to speak from it.

    Attributes:
        trailing_windows: How many of the user's most recent populated windows the summary covers.
            Thirty by default — roughly six working weeks, which is long enough to average over a
            month's work rhythm and short enough that a change of role or team stops being judged
            against the old one within a quarter. A bounded window is preferred over an all-time
            mean precisely so a *drifting but normal* user is not permanently anomalous.
        min_history_windows: Populated windows required before a baseline-relative read returns
            anything but `NEUTRAL_VALUE`. Eight by default, matching
            `phos.models.BehaviouralModel.min_samples`, so PHOS gives one answer to "how many
            points before you may claim a baseline" rather than two.
        trend_windows: Length of the series `TrailingHistory.trend` fits a slope to, counting the
            current window. Seven by default — one working week, so a weekly rhythm contributes one
            full cycle rather than a fraction of one.
        deviation_cap: Largest magnitude `TrailingHistory.deviation` may report. Ten by default:
            beyond ten trailing standard deviations the number has stopped being informative, and
            capping it keeps one pathological window from dominating the second-stage baseline that
            `phos.models` later learns over these features.

    Invariants:
        ``min_history_windows <= trailing_windows`` and ``trend_windows - 1 <= trailing_windows``.
        Either violation would define a feature that can never be computed, which is worse than a
        misconfiguration because it fails silently and forever.
    """

    model_config = ConfigDict(frozen=True)

    trailing_windows: int = Field(default=30, ge=1)
    min_history_windows: int = Field(default=8, ge=1)
    trend_windows: int = Field(default=7, ge=2)
    deviation_cap: float = Field(default=10.0, gt=0.0)

    @model_validator(mode="after")
    def _check_reachable(self) -> Self:
        """Reject a policy under which a feature could never leave its cold start."""
        if self.min_history_windows > self.trailing_windows:
            raise ValueError(
                f"min_history_windows={self.min_history_windows} exceeds "
                f"trailing_windows={self.trailing_windows}, so a baseline-relative feature would "
                "be neutral forever"
            )
        if self.trend_windows - 1 > self.trailing_windows:
            raise ValueError(
                f"trend_windows={self.trend_windows} needs {self.trend_windows - 1} past windows "
                f"but trailing_windows={self.trailing_windows} keeps fewer, so the trend would be "
                "neutral forever"
            )
        return self


class _RollingCounterparties:
    """The set of names one user has been seen with recently, as a bounded rolling window.

    A `set` would grow without bound over a corpus of any length and would make "new" mean "never
    seen since the beginning of time", which stops being a useful claim about a person after a few
    months. This keeps one set per window and a reference count across them, so eviction is exact:
    a name is forgotten when, and only when, the last window mentioning it falls out.
    """

    __slots__ = ("_counts", "_limit", "_windows")

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._windows: deque[frozenset[str]] = deque()
        self._counts: Counter[str] = Counter()

    @property
    def windows(self) -> int:
        """How many populated windows the memory currently holds."""
        return len(self._windows)

    def contains(self, name: str) -> bool:
        """Return whether ``name`` appears anywhere in the remembered windows."""
        return self._counts[name] > 0

    def push(self, names: frozenset[str]) -> None:
        """Remember one window's names, forgetting the oldest window if the memory is full."""
        if len(self._windows) == self._limit:
            for name in self._windows.popleft():
                if self._counts[name] <= 1:
                    del self._counts[name]
                else:
                    self._counts[name] -= 1
        self._windows.append(names)
        self._counts.update(names)


class TrailingHistory:
    """One user's own recent past, per feature and per counterparty kind.

    Mutable by design and deliberately not a Pydantic model: it is written once per user-window over
    hundreds of thousands of windows, and it is run state rather than a value in the ontology. It is
    created inside the call that uses it and never shared, so there is no global mutable state
    (Constitution §6).

    The reading methods — `deviation`, `difference`, `trend`, `new_counterparties` — are pure with
    respect to this object. `observe` is the only mutator.

    Attributes:
        policy: The window lengths and the cap this history was built with.
    """

    __slots__ = ("_counterparties", "_series", "policy")

    def __init__(self, policy: HistoryPolicy | None = None) -> None:
        """Create an empty history.

        Args:
            policy: Window lengths and the deviation cap. Defaults to `HistoryPolicy`.
        """
        self.policy = policy or HistoryPolicy()
        self._series: dict[tuple[str, str], deque[float]] = {}
        self._counterparties: dict[tuple[str, str], _RollingCounterparties] = {}

    # --------------------------------------------------------------------------------------------
    # Reading — pure, and strictly about windows before the current one
    # --------------------------------------------------------------------------------------------

    def deviation(self, user_id: str, feature: str, value: float) -> float:
        """Return ``value`` as a signed z-score against this user's own trailing history.

        This is the highest-value enrichment in PART 6A: it turns "logged on 40 times" into "logged
        on six standard deviations above their own norm", which is the form an insider's tell
        actually takes.

        Args:
            user_id: The corpus's own identifier for the user.
            feature: The feature the value measures.
            value: The current window's value, which is **not** part of the baseline it is judged
                against.

        Returns:
            ``(value - trailing_mean) / trailing_stddev``, clamped to ±`HistoryPolicy.deviation_cap`
            and **signed**, so a collapse in activity is distinguishable from a spike. Special
            cases, all documented policy rather than accident:

            - Fewer than `HistoryPolicy.min_history_windows` past windows: `NEUTRAL_VALUE`.
            - A trailing standard deviation of zero and ``value`` equal to the mean: ``0.0``.
            - A trailing standard deviation of zero and any other value: the cap, signed. The
              departure is real and unmeasurable in standard deviations, so it is reported at the
              ceiling rather than as an infinity.

        Note:
            The standard deviation is the population one (``ddof=0``), matching
            `phos.models.GaussianBaseline`, so a z-score means the same thing everywhere in PHOS.
        """
        window = self._series.get((user_id, feature))
        if window is None or len(window) < self.policy.min_history_windows:
            return NEUTRAL_VALUE
        values = tuple(window)
        mean = math.fsum(values) / len(values)
        variance = math.fsum((point - mean) ** 2 for point in values) / len(values)
        stddev = math.sqrt(variance)
        cap = self.policy.deviation_cap
        if stddev == 0.0:
            return 0.0 if value == mean else math.copysign(cap, value - mean)
        return max(-cap, min(cap, (value - mean) / stddev))

    def difference(self, user_id: str, feature: str, value: float) -> float:
        """Return ``value`` minus the same feature's value in this user's prior populated window.

        The level says where someone is; the first difference says that they moved, which is what
        CERT's own scenario descriptions are written in terms of — a user who "begins" working
        after hours, or uses a thumb drive "at markedly higher rates than their previous activity".

        Args:
            user_id: The corpus's own identifier for the user.
            feature: The feature the value measures.
            value: The current window's value.

        Returns:
            The step since the previous populated window, or `NEUTRAL_VALUE` when this is the
            user's first window for this feature.

        Note:
            "Prior populated window" is the previous window this user was *active* in, not the
            previous calendar day. The featuriser emits nothing for an idle day, so a weekend
            closes rather than reading as a fall to zero and back.
        """
        window = self._series.get((user_id, feature))
        if not window:
            return NEUTRAL_VALUE
        return value - window[-1]

    def trend(self, user_id: str, feature: str, value: float) -> float:
        """Return the least-squares slope of this feature over the recent windows, including now.

        A first difference sees a step and misses a climb: scenario 4 of CERT r3.1 escalates "more
        and more frequently over a 3 month period", where each day's change is small and the
        direction is the signal. The slope is that direction, in feature units per populated window.

        Args:
            user_id: The corpus's own identifier for the user.
            feature: The feature the value measures.
            value: The current window's value, which is the last point of the fitted series.

        Returns:
            The slope over the last `HistoryPolicy.trend_windows` populated windows, or
            `NEUTRAL_VALUE` when there are not yet that many.

        Note:
            Including the current window is not a causality violation — a first difference reads it
            too. What causality forbids is reading the *future*, and folding the current window into
            the *baseline* it is judged against; neither happens here.

            The series is indexed by populated window, not by date, so the x-axis is "the user's
            recent active days" and a gap does not stretch the slope.
        """
        length = self.policy.trend_windows
        window = self._series.get((user_id, feature))
        past = tuple(window)[-(length - 1) :] if window else ()
        if len(past) < length - 1:
            return NEUTRAL_VALUE
        series = (*past, value)
        centre = (length - 1) / 2.0
        # Sxx for x = 0..length-1 is length * (length^2 - 1) / 12, a constant for a fixed window,
        # and sum((x - mean_x) * mean_y) is zero, so the covariance needs only one pass.
        covariance = math.fsum((index - centre) * point for index, point in enumerate(series))
        spread = length * (length * length - 1) / 12.0
        return covariance / spread

    def new_counterparties(self, user_id: str, kind: str, seen: Collection[str]) -> float:
        """Return how many of ``seen`` this user has not been seen with recently.

        "New" means **new for this user**. A machine every one of their colleagues uses is still new
        to someone who has never logged into it, and that is the reading scenario 4 needs — a user
        who "logs into another user's machine". Nothing here consults another user's history; peer
        comparison is PART 6B.

        Args:
            user_id: The corpus's own identifier for the user.
            kind: Which sort of counterparty is being counted — machines and mail recipients are
                kept in separate memories so a new machine is not diluted by a new web host.
            seen: The names encountered in the current window.

        Returns:
            The count of names absent from the user's trailing memory, or `NEUTRAL_VALUE` before
            `HistoryPolicy.min_history_windows` populated windows. Everything is new to someone with
            no history, and counting that would report a fact about the corpus's start date rather
            than about the person.
        """
        memory = self._counterparties.get((user_id, kind))
        if memory is None or memory.windows < self.policy.min_history_windows:
            return NEUTRAL_VALUE
        return float(sum(1 for name in set(seen) if not memory.contains(name)))

    # --------------------------------------------------------------------------------------------
    # Writing — the only mutator, called after a window has been emitted
    # --------------------------------------------------------------------------------------------

    def observe(
        self,
        user_id: str,
        values: Mapping[str, float],
        counterparties: Mapping[str, Collection[str]],
    ) -> None:
        """Fold one completed window into this user's history.

        Call this **after** every feature for the window has been read, never before. That ordering
        is the causality guarantee, and `phos.sentiel.featurise` is the only caller that has to
        honour it.

        Args:
            user_id: The corpus's own identifier for the user.
            values: The window's value for each feature that has a trailing history.
            counterparties: The window's names for each counterparty kind. A kind mapped to an empty
                collection still counts as a populated window, so a quiet user still accumulates the
                history their cold start is waiting for.
        """
        for feature, value in values.items():
            key = (user_id, feature)
            window = self._series.get(key)
            if window is None:
                window = deque(maxlen=self.policy.trailing_windows)
                self._series[key] = window
            window.append(value)

        for kind, names in counterparties.items():
            key = (user_id, kind)
            memory = self._counterparties.get(key)
            if memory is None:
                memory = _RollingCounterparties(self.policy.trailing_windows)
                self._counterparties[key] = memory
            memory.push(frozenset(names))
