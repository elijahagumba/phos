"""Black-box query interface to Atlas, for the breaker to use (PART S7).

The breaker reaches Atlas only through this interface: it gets exactly what a user of Atlas
would see — alerts, hypotheses and confidences — and never rules, weights, thresholds, source
code or labels. Every query is counted against a configurable budget.

This module lives in the referee package because S7 says the referee supplies it, and because the
breaker must never import Atlas internals. The referee itself never imports the breaker, so the
dependency direction is one way: breaker -> referee -> (atlas, synth).
"""

from __future__ import annotations

from dataclasses import dataclass

from phos.eval import Detection, Detector
from phos.referee.corpus import load_plant_dataset
from phos.referee.detectors import AtlasDetector, leading_hypothesis
from phos.synth.outputs import GeneratedPlant


@dataclass(frozen=True)
class QueryResult:
    """What one query returns: what a user of Atlas would see, nothing more.

    Attributes:
        detections: One ``Detection`` per narrative that resolved to evidence — timestamp,
            score, confidence, entity ids. No labels, no seed, no ground truth.
        hypotheses: The leading hypothesis's template id and confidence, for each narrative.
            ``None`` confidence means the engine reported insufficient evidence.
        queries_used: Always 1 — one query per call, so the caller can count.
    """

    detections: tuple[Detection, ...]
    hypotheses: tuple[tuple[str, float | None], ...]
    queries_used: int = 1


class QueryInterface:
    """A counted, black-box way to ask Atlas about one plant.

    The breaker constructs one of these per plant it wants to probe, calls :meth:`ask` once per
    probe, and never sees anything but what :meth:`ask` returns. The query counter is the only
    record of how many times the breaker looked.

    Attributes:
        detector: Anything satisfying :class:`phos.eval.Detector`. When it is an
            :class:`phos.referee.detectors.AtlasDetector`, the leading hypothesis of each
            narrative is also returned.
        queries_used: How many times :meth:`ask` has been called on this interface.
    """

    def __init__(self, detector: Detector, budget: int | None = None) -> None:
        """Create an interface over ``detector`` with an optional query budget.

        Args:
            detector: The detector to query — treated as a black box.
            budget: Maximum queries allowed, or ``None`` for unlimited. A budget of 0 refuses
                every query.
        """
        self._detector = detector
        self._budget = budget
        self._queries_used = 0

    @property
    def detector(self) -> Detector:
        """The detector being queried (read-only)."""
        return self._detector

    @property
    def queries_used(self) -> int:
        """How many :meth:`ask` calls have been made."""
        return self._queries_used

    @property
    def queries_remaining(self) -> int | None:
        """Queries left under the budget, or ``None`` for unlimited."""
        if self._budget is None:
            return None
        return max(0, self._budget - self._queries_used)

    def ask(self, plant: GeneratedPlant) -> QueryResult:
        """Run the detector against ``plant`` and return what Atlas would show a user.

        The plant's capture file (``capture.pcap`` alongside its telemetry) is passed to the
        detector so it can build command evidence from the control traffic — without the breaker
        ever seeing the capture or the labels.

        Args:
            plant: A generated plant, already written to disk.

        Returns:
            The detector's output: detections and leading hypotheses, with no labels or seeds.

        Raises:
            BudgetExceededError: If the query budget would be exceeded.
        """
        if self._budget is not None and self._queries_used >= self._budget:
            raise BudgetExceededError(
                f"query budget of {self._budget} exhausted ({self._queries_used} used)"
            )
        dataset = load_plant_dataset(plant)
        detections = tuple(self._detector.run(dataset))

        hypotheses: list[tuple[str, float | None]] = []
        if isinstance(self._detector, AtlasDetector):
            store = self._detector.last_store
            if store is not None:
                hypotheses_by_id = {item.id: item for item in store.hypotheses()}
                for narrative in self._detector.last_narratives:
                    leader = leading_hypothesis(narrative, hypotheses_by_id)
                    hypotheses.append(
                        (
                            leader.template_id,
                            leader.confidence,
                        )
                        if leader is not None
                        else ("", None)
                    )
        self._queries_used += 1
        return QueryResult(
            detections=detections,
            hypotheses=tuple(hypotheses),
            queries_used=self._queries_used,
        )


class BudgetExceededError(RuntimeError):
    """Raised when a query would exceed the configured budget."""


__all__ = ["BudgetExceededError", "QueryInterface", "QueryResult"]
