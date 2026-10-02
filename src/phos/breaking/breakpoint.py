"""The breaking point: where each attack type crosses from caught to missed.

The headline finding of D3 is not an accuracy number. A blended score over seventy-six attacks
would average a type Atlas catches at every subtlety together with one it never sees at all, and
report a middling number describing neither. What an engineer can act on is the **boundary**: for
each attack type, the point on D2's difficulty dial where Atlas stops seeing it.

So results are grouped by type, swept by subtlety, and reduced to two numbers — the hardest attack
still caught and the easiest one missed. Between them lies the breaking point.

**Three ways this reduction could lie, and what stops each.**

*Pooling plants.* A row is keyed by ``(plant, type, fingerprint status)``, not by type alone. The
same attack type against a different machine — different baseline, different daily rhythm, different
signals — is a different measurement, and averaging the three shipped plants into one row per type
makes every row look ragged whether it is or not: "missed at 0.00" from one plant beside "caught at
0.99" from another is not a sweep, it is two sweeps stacked. That is the same blending the PART
warned against, one level up, so the plant is part of the key.

*Pretending a boundary exists when the results are ragged.* Even within one plant, real sweeps are
not always monotone: a type can be caught at 0.6, missed at 0.3, and caught again at 0.9, because
each band sits at a different hour of the plant's day and the plant is not equally observable at
every hour — D2 warned about exactly this. A single "breaks at 0.45" would be fiction. `monotone`
says whether the sweep was clean, and a ragged row is reported as a range with its raggedness on the
face of it.

*Blending clean results with fingerprint-caveated ones.* A type whose manipulation carries D2's
documented residual cannot contribute to the headline map, so `breaking_points` splits by
fingerprint status and never pools the two. A caveated row is a real row, printed in its own
section with the caveat attached.

*Counting the anti-fingerprint control as a miss.* An attack at subtlety 1.0 has exactly zero
magnitude. It is not a miss and it is not a catch; it is the control that proves the injection
leaves no tell. Inert outcomes are excluded from the boundary arithmetic and reported separately,
where a *detection* on one would be the most important finding in the report.
"""

import logging
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from phos.breaking.fingerprint import FingerprintStatus
from phos.breaking.outcome import AttackOutcome, DetectionVerdict
from phos.synth.attacks import AttackType

__all__ = ["BreakingPoint", "breaking_points"]

logger = logging.getLogger(__name__)


class BreakingPoint(BaseModel):
    """Where one type, on one plant, at one fingerprint status, goes from caught to missed.

    Attributes:
        plant_id: The plant this sweep was run against. Part of the key, because a breaking point is
            a property of a type *on a machine* — see the module docstring.
        attack_type: The type this row describes.
        fingerprint: Whether these results are clean evidence or carry D2's residual. A type can
            appear twice — once per status — when its targets differ across plants, and the two
            rows are never pooled.
        outcomes: Every non-inert outcome for this type, easiest first.
        inert: The zero-magnitude controls, kept out of the arithmetic and reported separately.
        caught_hardest: Highest subtlety still caught, or ``None`` if nothing was caught.
        missed_easiest: Lowest subtlety missed, or ``None`` if nothing was missed.
        monotone: Whether the sweep was clean — every catch below every miss. False means the
            boundary is a range with holes in it rather than a point, and must be read as one.
        n_dangerous_misses: Misses where D1's true-state record shows the plant went somewhere
            unattacked operation never reached. The count that matters most on the row.
        detected_inert: Inert controls that nonetheless produced an alert. Should be zero; any
            other value is evidence of a leaked fingerprint and is the most important number here.

    Invariants:
        Counts agree with the outcomes they summarise, so a row cannot claim a boundary its
        outcomes do not support.
    """

    model_config = ConfigDict(frozen=True)

    plant_id: str = ""
    attack_type: AttackType
    fingerprint: FingerprintStatus
    outcomes: tuple[AttackOutcome, ...] = ()
    inert: tuple[AttackOutcome, ...] = ()
    caught_hardest: float | None = None
    missed_easiest: float | None = None
    monotone: bool = True
    n_dangerous_misses: int = Field(default=0, ge=0)
    detected_inert: int = Field(default=0, ge=0)

    @property
    def n_caught(self) -> int:
        """How many real attacks of this type Atlas caught."""
        return sum(1 for outcome in self.outcomes if outcome.verdict is DetectionVerdict.CAUGHT)

    @property
    def n_missed(self) -> int:
        """How many real attacks of this type Atlas missed, dangerous or not."""
        return sum(1 for outcome in self.outcomes if outcome.is_miss)

    @property
    def blind_everywhere(self) -> bool:
        """Whether Atlas caught none of this type at any subtlety, including the blatant end.

        The most serious shape a row can take: not a boundary but a whole category the engine
        cannot see. There is no breaking point to report, because it never worked.
        """
        return bool(self.outcomes) and self.caught_hardest is None

    @property
    def caught_everywhere(self) -> bool:
        """Whether Atlas caught every real attack of this type, down to the hardest one shipped.

        Not a claim that no breaking point exists — only that the shipped battery did not reach it.
        The honest reading is "below the hardest subtlety tested", not "always".
        """
        return bool(self.outcomes) and self.missed_easiest is None

    def describe(self) -> str:
        """Return the boundary in one sentence, hedged exactly as far as the evidence requires."""
        if not self.outcomes:
            return "no non-inert attacks of this type were run"
        if self.blind_everywhere:
            hardest = min(outcome.subtlety for outcome in self.outcomes)
            return (
                f"blind at every subtlety tested, including {hardest:.2f} — no breaking point, "
                "the whole type is unseen"
            )
        if self.caught_everywhere:
            hardest = max(outcome.subtlety for outcome in self.outcomes)
            return (
                f"caught at every subtlety tested, down to {hardest:.2f}; the battery did not "
                "reach its limit"
            )
        assert self.caught_hardest is not None and self.missed_easiest is not None
        if not self.monotone:
            return (
                f"ragged between {self.missed_easiest:.2f} and {self.caught_hardest:.2f}: missed "
                f"at {self.missed_easiest:.2f} yet still caught at {self.caught_hardest:.2f}, so "
                "the boundary is a range with holes rather than a point"
            )
        return f"breaks between {self.caught_hardest:.2f} and {self.missed_easiest:.2f}"


def breaking_points(outcomes: Sequence[AttackOutcome]) -> tuple[BreakingPoint, ...]:
    """Reduce per-attack outcomes to one boundary row per plant, type and fingerprint status.

    Args:
        outcomes: Every detection outcome measured, from any number of corpora.

    Returns:
        One row per ``(plant, type, fingerprint status)`` present, ordered by those three, so a
        caveated row never sits silently beside a clean one and two plants never share a sweep.

    Note:
        Pure. Takes measurements and returns a summary; runs nothing and reads nothing from disk.
    """
    grouped: dict[tuple[str, AttackType, FingerprintStatus], list[AttackOutcome]] = {}
    for outcome in outcomes:
        key = (outcome.plant_id, outcome.attack_type, outcome.fingerprint.status)
        grouped.setdefault(key, []).append(outcome)

    rows: list[BreakingPoint] = []
    for (plant_id, attack_type, status), members in sorted(
        grouped.items(), key=lambda item: (item[0][0], item[0][1].value, item[0][2].value)
    ):
        real = sorted(
            (outcome for outcome in members if not outcome.is_inert),
            key=lambda outcome: (outcome.subtlety, outcome.attack_id),
        )
        inert = sorted(
            (outcome for outcome in members if outcome.is_inert),
            key=lambda outcome: outcome.attack_id,
        )
        caught = [
            outcome.subtlety for outcome in real if outcome.verdict is DetectionVerdict.CAUGHT
        ]
        missed = [outcome.subtlety for outcome in real if outcome.is_miss]

        caught_hardest = max(caught) if caught else None
        missed_easiest = min(missed) if missed else None
        rows.append(
            BreakingPoint(
                plant_id=plant_id,
                attack_type=attack_type,
                fingerprint=status,
                outcomes=tuple(real),
                inert=tuple(inert),
                caught_hardest=caught_hardest,
                missed_easiest=missed_easiest,
                monotone=(
                    caught_hardest is None
                    or missed_easiest is None
                    or caught_hardest < missed_easiest
                ),
                n_dangerous_misses=sum(
                    1 for outcome in real if outcome.verdict is DetectionVerdict.MISSED_DANGEROUS
                ),
                detected_inert=sum(1 for outcome in inert if outcome.detected),
            )
        )

    logger.debug("reduced %d outcome(s) to %d breaking-point row(s)", len(outcomes), len(rows))
    return tuple(rows)
