"""The valve law as a set of values, and how a sample is read against it.

These are the types `phos.atlas.code_law.derive` fills from the controller
source. They hold no threshold of PHOS's own: every number in them was read out
of the pinned source and carries the file and line it came from.

**The guard and the release literal are two different facts, kept apart.** The
guard is what ``_check_manual_input`` states: the comparison runs unless the
mode is one it names manual. The release literal is a tag default from the tag
table. The hand-written ``controller_valve`` states instead that the comparison
runs only when the mode equals the release literal. Those agree on every mode
the guard names and on the release default, and part ways on any other value.
ADR 0370 named that divergence; ADR 0382 asks for a guard type that can hold
both shapes so the forms can be compared without trying modes.

**Forced actuator writes are a third fact.** At modes 1 and 2 the same guard
function writes the actuator before returning true. The derivation reports
those writes on the law. They are not folded into the comparison rule and they
are not dropped (ADR 0382 bar 4).

There is no score, confidence, probability, weight or magnitude on any of these
types, and no field that could hold one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from phos.atlas.declared_law import ControllerSample

__all__ = [
    "SAMPLE_FIELDS",
    "DerivedBranch",
    "DerivedCondition",
    "DerivedForcedWrite",
    "DerivedGuard",
    "DerivedLiteral",
    "DerivedRule",
    "DerivedValveLaw",
    "GuardForm",
    "Side",
    "condition_holds",
    "sample_values",
]

#: ICSSim tag name to the `ControllerSample` field that carries it. Declared, so
#: no field is chosen from the shape of a tag's name.
SAMPLE_FIELDS: Final[Mapping[str, str]] = {
    "tank_level_value": "level",
    "tank_level_min": "level_min",
    "tank_level_max": "level_max",
    "tank_input_valve_status": "input_valve",
    "tank_input_valve_mode": "input_mode",
    "bottle_level_value": "bottle_level",
    "bottle_level_max": "bottle_max",
    "bottle_distance_to_filler_value": "belt",
    "tank_output_valve_status": "output_valve",
    "tank_output_valve_mode": "output_mode",
}


class Side(StrEnum):
    """Which valve a rule writes. The words the hand-written law already uses."""

    INPUT = "input valve"
    OUTPUT = "output valve"


class GuardForm(StrEnum):
    """The shape of a guard, inspected without trying modes (ADR 0382 bar 3).

    An exclusion list states the comparison when the mode is not in a finite
    set. An equality states it when the mode equals one value. A form that can
    hold only one of these cannot represent the other, and cannot meet the bar
    that asks both shapes be named.
    """

    EXCLUSION = "exclusion"
    EQUALITY = "equality"


@dataclass(frozen=True)
class DerivedLiteral:
    """One constant read out of the source, with where it was read.

    Attributes:
        name: ``close``, ``open``, ``release_mode`` or ``belt_past_filler``.
        value: The number, as a float.
        literal_text: How the source writes it at the cited node, so an integer
            in the source is visible as an integer. Never rebuilt from ``value``.
        file: The declared file it came from.
        line: The line in that file, counting from one.
    """

    name: str
    value: float
    literal_text: str
    file: str
    line: int


@dataclass(frozen=True)
class DerivedForcedWrite:
    """One actuator write ``_check_manual_input`` forces at a named mode.

    Attributes:
        mode: The mode that triggers the write.
        value: The value written to the actuator.
        literal_text: How the source writes that value at the cited node.
        file: The declared file it came from.
        line: The line of the ``_set`` call.
    """

    mode: float
    value: float
    literal_text: str
    file: str
    line: int


@dataclass(frozen=True)
class DerivedGuard:
    """A guard that holds either an exclusion list or an equality (ADR 0382).

    The derived guard from ``_check_manual_input`` is an exclusion: the
    comparison runs at every mode not in ``manual_modes``. The hand guard from
    ``controller_valve`` is an equality: the comparison runs only when the mode
    equals ``equals_mode``. The two shapes live in one type so their forms can
    be compared without trying values.

    Exactly one of ``manual_modes`` and ``equals_mode`` is set. A constructor
    that sets both, or neither, is refused.

    Attributes:
        form: Which shape this guard is, answered without trying modes.
        manual_modes: The modes an exclusion excludes, in source order, or ().
        equals_mode: The single mode an equality states, or None.
        file: The declared file it came from, or a name for a hand-built guard.
        line: The line the guard is defined on, or 0 for a hand-built guard.
    """

    form: GuardForm
    manual_modes: tuple[float, ...]
    equals_mode: float | None
    file: str
    line: int

    def __post_init__(self) -> None:
        """Refuse a guard that is not exactly one of the two shapes."""
        has_exclusion = len(self.manual_modes) > 0
        has_equality = self.equals_mode is not None
        if self.form is GuardForm.EXCLUSION:
            if not has_exclusion or has_equality:
                raise ValueError("an exclusion guard names manual modes and no equals mode")
            return
        if self.form is GuardForm.EQUALITY:
            if has_exclusion or not has_equality:
                raise ValueError("an equality guard names an equals mode and no manual modes")
            return
        raise ValueError(f"unknown guard form: {self.form!r}")

    @classmethod
    def exclusion(cls, manual_modes: tuple[float, ...], *, file: str, line: int) -> DerivedGuard:
        """Return an exclusion-list guard stated when the mode is not in the list.

        Args:
            manual_modes: The modes the source returns true for, in source order.
            file: The declared file the modes were read from.
            line: The line the guard is defined on.

        Returns:
            A guard whose form is exclusion.

        Raises:
            ValueError: If ``manual_modes`` is empty.
        """
        if not manual_modes:
            raise ValueError("an exclusion guard names at least one manual mode")
        return cls(
            form=GuardForm.EXCLUSION,
            manual_modes=manual_modes,
            equals_mode=None,
            file=file,
            line=line,
        )

    @classmethod
    def equality(cls, equals_mode: float, *, file: str, line: int) -> DerivedGuard:
        """Return an equality guard stated when the mode equals ``equals_mode``.

        Args:
            equals_mode: The single mode the comparison is stated at.
            file: Where the equality was read, or a name for a hand-built guard.
            line: The line it was read from, or 0 for a hand-built guard.

        Returns:
            A guard whose form is equality.
        """
        return cls(
            form=GuardForm.EQUALITY,
            manual_modes=(),
            equals_mode=equals_mode,
            file=file,
            line=line,
        )

    def states(self, mode: float) -> bool:
        """Return whether the comparison runs at ``mode``."""
        if self.form is GuardForm.EXCLUSION:
            return mode not in self.manual_modes
        return mode == self.equals_mode

    def states_only(self, value: float) -> bool:
        """Return whether the stated set is exactly ``{value}``.

        This is a question about the guard's *form*, answered without trying
        values. An exclusion of a finite list states every other number, so it
        is never exactly one value. An equality answers true only when its
        equals mode is ``value``.

        Args:
            value: The single mode the caller expects to be stated.

        Returns:
            True only for an equality whose equals mode is ``value``.
        """
        if self.form is GuardForm.EQUALITY:
            return self.equals_mode == value
        return False

    def differs_in_form_from(self, other: DerivedGuard) -> bool:
        """Return whether this guard and ``other`` have different forms.

        The check inspects ``form``. It does not try modes.

        Args:
            other: Another guard.

        Returns:
            True when the two forms are not the same.
        """
        return self.form is not other.form


@dataclass(frozen=True)
class DerivedCondition:
    """One comparison the source makes.

    Attributes:
        left: The tag on the left.
        operator: The comparison as the source writes it, for example ``>``.
        right_signal: The tag on the right, or None when the right side is a
            literal.
        right_literal: The literal on the right, or None when it is a tag.
        right_literal_text: How the source writes the right literal, or None
            when the right side is a tag. Taken from the cited node, never
            rebuilt from ``right_literal``.
        line: The line the comparison is on.
    """

    left: str
    operator: str
    right_signal: str | None
    right_literal: float | None
    right_literal_text: str | None
    line: int


@dataclass(frozen=True)
class DerivedBranch:
    """One branch of a rule: conditions joined by ``or``, and what it writes.

    Attributes:
        conditions: The comparisons, in source order. Any one of them being
            true takes the branch, which is what ``or`` means.
        writes: The value the branch writes to the valve.
        line: The line the branch's test is on.
    """

    conditions: tuple[DerivedCondition, ...]
    writes: float
    line: int

    def holds(self, values: Mapping[str, float]) -> bool:
        """Return whether any condition in this branch is true for ``values``."""
        return any(condition_holds(condition, values) for condition in self.conditions)


@dataclass(frozen=True)
class DerivedRule:
    """One valve's rule: ordered branches, then what the source does otherwise.

    Attributes:
        side: Which valve this writes.
        branches: The branches in source order. The first whose conditions hold
            is the one that writes.
        otherwise: The value written when no branch holds, or None when the
            source writes nothing, which is silence, not a default.
        mode_signal: The mode tag the guard was given for this side.
        status_signal: The valve tag the rule writes.
    """

    side: Side
    branches: tuple[DerivedBranch, ...]
    otherwise: float | None
    mode_signal: str
    status_signal: str


@dataclass(frozen=True)
class DerivedValveLaw:
    """The valve law as the source states it.

    Attributes:
        literals: The four constants, each with its provenance.
        guard: The modes the source calls manual, as an exclusion.
        forced_writes: The actuator writes the guard forces at modes 1 and 2,
            in source order. A separate stated fact (ADR 0382 bar 4).
        rules: The input rule then the output rule.
        commit: The pinned commit the source came from.
        digests: The sha256 of each file read, by relative path.
    """

    literals: tuple[DerivedLiteral, ...]
    guard: DerivedGuard
    forced_writes: tuple[DerivedForcedWrite, ...]
    rules: tuple[DerivedRule, ...]
    commit: str
    digests: Mapping[str, str]

    def literal(self, name: str) -> DerivedLiteral:
        """Return the named literal.

        Args:
            name: ``close``, ``open``, ``release_mode`` or ``belt_past_filler``.

        Returns:
            That literal.

        Raises:
            KeyError: If the derivation holds no literal of that name.
        """
        for literal in self.literals:
            if literal.name == name:
                return literal
        raise KeyError(name)

    def rule(self, side: Side) -> DerivedRule:
        """Return the rule for ``side``.

        Args:
            side: Which valve.

        Returns:
            That side's rule.

        Raises:
            KeyError: If the derivation holds no rule for that side.
        """
        for rule in self.rules:
            if rule.side is side:
                return rule
        raise KeyError(side)

    def stated(self, sample: ControllerSample) -> bool:
        """Return whether the source's guard lets the comparison run.

        Both mode tags must be outside the manual list, because each side of
        the source is guarded separately and the law is one law.

        Args:
            sample: One controller sample.

        Returns:
            True when neither mode is one the guard names manual.
        """
        values = sample_values(sample)
        return all(self.guard.states(values[rule.mode_signal]) for rule in self.rules)

    def required(self, sample: ControllerSample, side: Side) -> float | None:
        """Return the value the source writes to ``side``, or None for silence.

        Args:
            sample: One controller sample.
            side: Which valve.

        Returns:
            The value the first holding branch writes, the rule's otherwise
            value when no branch holds, or None when the source writes nothing.
        """
        rule = self.rule(side)
        values = sample_values(sample)
        for branch in rule.branches:
            if branch.holds(values):
                return branch.writes
        return rule.otherwise

    def fired(self, sample: ControllerSample, side: Side) -> DerivedBranch | None:
        """Return the branch that decided ``side``, or None when none held.

        Args:
            sample: One controller sample.
            side: Which valve.

        Returns:
            The first holding branch, or None.
        """
        values = sample_values(sample)
        for branch in self.rule(side).branches:
            if branch.holds(values):
                return branch
        return None


def sample_values(sample: ControllerSample) -> Mapping[str, float]:
    """Return a controller sample keyed by ICSSim tag name.

    Args:
        sample: One controller sample.

    Returns:
        Each declared tag name mapped to that sample's value for it.
    """
    return {tag: float(getattr(sample, field)) for tag, field in SAMPLE_FIELDS.items()}


def condition_holds(condition: DerivedCondition, values: Mapping[str, float]) -> bool:
    """Return whether one derived comparison is true for ``values``.

    Only the comparisons the source is allowed to make are evaluated. An
    operator this function does not know is false, which refuses the branch
    rather than guessing what the source meant.

    Args:
        condition: One comparison read from the source.
        values: A sample keyed by tag name.

    Returns:
        Whether the comparison holds.
    """
    left = values[condition.left]
    if condition.right_signal is not None:
        right = values[condition.right_signal]
    elif condition.right_literal is not None:
        right = condition.right_literal
    else:  # pragma: no cover - a condition always has one right-hand side
        return False
    if condition.operator == ">":
        return left > right
    if condition.operator == "<":
        return left < right
    if condition.operator == ">=":
        return left >= right
    if condition.operator == "<=":
        return left <= right
    if condition.operator == "==":
        return left == right
    if condition.operator == "!=":
        return left != right
    return False
