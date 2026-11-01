"""Certificates: enough of the working that a person can recheck a break.

ADR 0370 bar 6: every break the derived law produces carries the law, the rows
it was evaluated on, and the comparison that came out false, so that anyone
holding the rows can recheck it without PHOS.

So a certificate holds:

- the law's name, which is the plant's word for it (ADR 0329);
- the rows the decision actually touched, each a tag name and the value in the
  sample, not the whole sample, so what mattered is visible;
- ``required_because``, the branch of the controller's own rule that fired,
  written as the comparison it is, or a note that no branch fired and the
  rule's otherwise value applies;
- ``comparison``, the equality between the valve and the required value that
  came out false. That is the break.

**There is no field that could hold a confidence, a probability, a weight, a
magnitude or a score**, and every sentence goes through `cited_statement`, which
refuses those words in any case (ADR 0323). A certificate is its own type: it
does not inherit from `LawBreak`, so page admission stays exactly
``type(item) is LawBreak`` (ADR 0322) and a certificate can never occupy one of
the eight slots.

The sentence is worded exactly as the hand-written law words it, so the two can
be compared sentence for sentence rather than through a parser.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from phos.atlas.code_law.law import (
    DerivedBranch,
    DerivedValveLaw,
    Side,
    sample_values,
)
from phos.atlas.declared_law import (
    CONTROLLER_VALVE,
    ControllerSample,
    LawBreak,
    cited_statement,
)

__all__ = [
    "CertificateRow",
    "CertifiedBreak",
    "Disagreement",
    "LawCertificate",
    "certified_breaks",
    "disagreement_certificate",
    "plain",
]

_NO_BRANCH = "no branch fired, so the rule's otherwise value applies"


def plain(number: float) -> str:
    """Render a value the way the plant writes a whole number.

    The hand-written law renders a valve value this way, and the derived law
    renders it the same way so the two sentences can be compared directly.

    Args:
        number: The value.

    Returns:
        The value with no trailing zeros.
    """
    return format(number, ".12g")


@dataclass(frozen=True)
class CertificateRow:
    """One tag the decision used, and its value in the sample.

    Attributes:
        signal: The tag name, as the controller's own table spells it.
        value: The value in the sample.
    """

    signal: str
    value: float


@dataclass(frozen=True)
class LawCertificate:
    """The working behind one break, checkable without PHOS.

    Attributes:
        law_name: The law the break is against.
        side: Which valve, in the words the law uses.
        at: When the sample was taken. Timezone-aware.
        rows: The tags the decision used, in a fixed order.
        required_because: The controller's own comparison that fired, or a note
            that none did.
        comparison: The equality between valve and required value that came out
            false.
        required: What the rule required.
        actual: What the valve was.
        statement: The law's name, then the fact, as the page would place it.
    """

    law_name: str
    side: str
    at: datetime
    rows: tuple[CertificateRow, ...]
    required_because: str
    comparison: str
    required: float
    actual: float
    statement: str


@dataclass(frozen=True)
class CertifiedBreak:
    """One break and the certificate that shows the working.

    Attributes:
        law_break: Exactly a `LawBreak`, so page admission is unchanged.
        certificate: The working behind it.
    """

    law_break: LawBreak
    certificate: LawCertificate


@dataclass(frozen=True)
class Disagreement:
    """One case where the derived law and the hand law part (ADR 0382 bar 5).

    A disagreement is not a `LawBreak`. It carries a certificate naming the
    law, the rows, and the comparison that came out false. There is no field
    that could hold a confidence, probability, weight, magnitude or score.

    Attributes:
        sample: The controller sample the two laws were evaluated on.
        kind: ``stated`` when they differ on whether the law is stated;
            ``actuator`` when they differ on the required actuator value.
        side: Which valve, when ``kind`` is ``actuator``; None otherwise.
        derived_stated: Whether the derived law stated the comparison.
        hand_stated: Whether the hand law stated the comparison.
        derived_required: What the derived law required, or None.
        hand_required: What the hand law required, or None.
        certificate: The working behind the parting.
    """

    sample: ControllerSample
    kind: str
    side: str | None
    derived_stated: bool
    hand_stated: bool
    derived_required: float | None
    hand_required: float | None
    certificate: LawCertificate


def disagreement_certificate(
    *,
    law_name: str,
    sample: ControllerSample,
    comparison: str,
    kind: str,
    side: str | None = None,
) -> LawCertificate:
    """Return a certificate for one disagreement on the extended enumeration.

    The text goes through `cited_statement`, which refuses score-words
    (ADR 0323). The certificate is not a `LawBreak` subclass (ADR 0322).

    Args:
        law_name: The law the two readings are of.
        sample: The rows the laws were evaluated on.
        comparison: The comparison that came out false.
        kind: ``stated`` or ``actuator``.
        side: Which valve, when the parting is on an actuator value.

    Returns:
        A certificate naming the law, the rows, and the false comparison.
    """
    values = dict(sample_values(sample))
    rows = (
        CertificateRow(signal="tank_input_valve_mode", value=values["tank_input_valve_mode"]),
        CertificateRow(signal="tank_output_valve_mode", value=values["tank_output_valve_mode"]),
        CertificateRow(signal="tank_level_value", value=values["tank_level_value"]),
        CertificateRow(signal="tank_level_min", value=values["tank_level_min"]),
        CertificateRow(signal="tank_level_max", value=values["tank_level_max"]),
        CertificateRow(signal="tank_input_valve_status", value=values["tank_input_valve_status"]),
        CertificateRow(signal="bottle_level_value", value=values["bottle_level_value"]),
        CertificateRow(signal="bottle_level_max", value=values["bottle_level_max"]),
        CertificateRow(
            signal="bottle_distance_to_filler_value",
            value=values["bottle_distance_to_filler_value"],
        ),
        CertificateRow(signal="tank_output_valve_status", value=values["tank_output_valve_status"]),
    )
    if kind == "stated":
        fact = (
            f"The derived guard and the hand guard part on whether the law is "
            f"stated at modes {plain(sample.input_mode)} and {plain(sample.output_mode)}."
        )
        because = "the guard comparison parted the two laws"
        required = 0.0
        actual = 0.0
    else:
        which = side if side is not None else "valve"
        fact = (
            f"The derived law and the hand law part on the required {which} "
            f"at modes {plain(sample.input_mode)} and {plain(sample.output_mode)}."
        )
        because = "the valve comparison parted the two laws"
        required = 0.0
        actual = 0.0
    statement = cited_statement(CONTROLLER_VALVE, fact)
    return LawCertificate(
        law_name=law_name,
        side=side if side is not None else "both valves",
        at=sample.at,
        rows=rows,
        required_because=because,
        comparison=comparison,
        required=required,
        actual=actual,
        statement=statement,
    )


def _branch_text(branch: DerivedBranch, values: dict[str, float]) -> str:
    """Write the branch that fired as the comparison it is."""
    parts: list[str] = []
    for condition in branch.conditions:
        left = f"{condition.left} {plain(values[condition.left])}"
        if condition.right_signal is not None:
            right = f"{condition.right_signal} {plain(values[condition.right_signal])}"
        else:
            right = plain(condition.right_literal if condition.right_literal is not None else 0.0)
        parts.append(f"{left} {condition.operator} {right}")
    return " or ".join(parts)


def _rows(law: DerivedValveLaw, side: Side, values: dict[str, float]) -> tuple[CertificateRow, ...]:
    """Return the tags this side's decision used, modes first, in a fixed order."""
    rule = law.rule(side)
    signals: list[str] = [other.mode_signal for other in law.rules]
    for branch in rule.branches:
        for condition in branch.conditions:
            signals.append(condition.left)
            if condition.right_signal is not None:
                signals.append(condition.right_signal)
    signals.append(rule.status_signal)
    seen: dict[str, None] = {}
    for signal in signals:
        seen.setdefault(signal, None)
    return tuple(CertificateRow(signal=signal, value=values[signal]) for signal in seen)


def certified_breaks(law: DerivedValveLaw, sample: ControllerSample) -> tuple[CertifiedBreak, ...]:
    """Return one certified break per side whose valve is not what the rule writes.

    A sample the law does not state produces nothing: that is silence, not a
    break. A side whose rule requires nothing produces nothing. Breaks come back
    input side first, which is the order the source states the two rules in.

    Args:
        law: The derived law.
        sample: One controller sample.

    Returns:
        Zero, one or two certified breaks.
    """
    if not law.stated(sample):
        return ()
    values = dict(sample_values(sample))
    found: list[CertifiedBreak] = []
    for side in Side:
        rule = law.rule(side)
        required = law.required(sample, side)
        if required is None:
            continue
        actual = values[rule.status_signal]
        if actual == required:
            continue
        branch = law.fired(sample, side)
        because = _NO_BRANCH if branch is None else _branch_text(branch, values)
        statement = cited_statement(
            CONTROLLER_VALVE,
            f"The {side.value} is {plain(actual)}, and the rule required {plain(required)}.",
        )
        found.append(
            CertifiedBreak(
                law_break=LawBreak(name=CONTROLLER_VALVE.name, time=sample.at, statement=statement),
                certificate=LawCertificate(
                    law_name=CONTROLLER_VALVE.name,
                    side=side.value,
                    at=sample.at,
                    rows=_rows(law, side, values),
                    required_because=because,
                    comparison=(f"{rule.status_signal} {plain(actual)} == {plain(required)}"),
                    required=required,
                    actual=actual,
                    statement=statement,
                ),
            )
        )
    return tuple(found)
