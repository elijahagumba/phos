"""ADR 0382's seven bars, computed from a derived law and a hand-written one.

Each bar is met or not met. There is no partial credit, no tuning knob, and
nothing here returns a fraction, a rate or a coverage figure that could be
restated as one.

Bars 1 to 6 are computed. **Bar 7 is not**: it is the suite, `mypy --strict`,
`ruff` and an empty diff on ``declared_law.py``, which are commands a session
runs and reports, not something this module can honestly assert about itself.
It is reported as not computed, so a report cannot read as seven met when six
were checked.

Bar 3 is decided from the *form* of the guard, not by trying modes. The derived
guard is an exclusion list; the hand guard is an equality. The bar asks that
each be the shape ADR 0382 names, and that the two differ; it is answered by
inspecting ``form``. A type that can hold only an exclusion list cannot meet
this bar, because it cannot represent the equality.

Bar 4 is the forced actuator writes at modes 1 and 2, which must be a stated
fact on the derived law. Dropping them fails the bar.

Bar 5 lists every disagreement on the extended enumeration, each with a
certificate. Omitting a disagreement fails the bar. Editing either law so the
list is empty fails the bar.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from phos.atlas.code_law.certificate import (
    CertificateRow,
    Disagreement,
    LawCertificate,
    certified_breaks,
    disagreement_certificate,
    plain,
)
from phos.atlas.code_law.law import (
    DerivedBranch,
    DerivedCondition,
    DerivedGuard,
    DerivedValveLaw,
    GuardForm,
    Side,
)
from phos.atlas.declared_law import (
    CONTROLLER_VALVE,
    ControllerSample,
    LawBreak,
    LawRegister,
    Standing,
    assess_plant,
    law_page,
)

__all__ = [
    "BAR_NAMES",
    "ENUMERATION_MODES",
    "ENUMERATION_SEED",
    "EXPECTED_CASE_COUNT",
    "AgreementResult",
    "BarResult",
    "HandGuard",
    "check_agreement",
    "enumerate_samples",
    "guard_forms_meet_bar",
    "hand_guard",
]

#: ADR 0382's seed. The enumeration below is exhaustive over the declared cases,
#: so nothing is sampled and no ordering needs it. It is recorded, not used.
ENUMERATION_SEED: Final = 20261030

#: The seven modes ADR 0382 names on each of the two mode tags.
ENUMERATION_MODES: Final[tuple[float, ...]] = (0.0, 1.0, 2.0, 3.0, 3.3, 4.0, 100.0)

#: 5 levels x 3 bottles x 3 belts x 7 input modes x 7 output modes x 2 x 2.
EXPECTED_CASE_COUNT: Final = 8820

#: The bars, in the order ADR 0382 lists them.
BAR_NAMES: Final[tuple[str, ...]] = (
    "literal agreement, quoted from the source node",
    "comparison agreement on both sides",
    "guard comparison is on the guard's form",
    "forced actuator writes at modes 1 and 2 are a stated fact",
    "every disagreement on the extended enumeration is listed, with a certificate",
    "certificate shape",
    "the tree stays green",
)

_SCORE_WORDS: Final[tuple[str, ...]] = (
    "confidence",
    "probability",
    "weight",
    "magnitude",
    "score",
)

LEVEL_MIN: Final = 3.0
LEVEL_MAX: Final = 7.0
BOTTLE_MAX: Final = 1.8
_AT: Final = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
_REGISTER: Final = LawRegister(laws=(CONTROLLER_VALVE,))

_EXPECTED_LITERALS: Final[tuple[tuple[str, float, str], ...]] = (
    ("close", 0.0, "0"),
    ("open", 1.0, "1"),
    ("release_mode", 3.0, "3"),
    ("belt_past_filler", 1.0, "1.0"),
)

#: Forced writes ADR 0382 bar 4 names: close at mode 1.0, open at mode 2.0.
_EXPECTED_FORCED: Final[tuple[tuple[float, float, str], ...]] = (
    (1.0, 0.0, "0"),
    (2.0, 1.0, "1"),
)

#: Where the hand equality is recorded for provenance on the hand guard.
_HAND_GUARD_FILE: Final = "src/phos/atlas/declared_law.py"


@dataclass(frozen=True)
class BarResult:
    """One bar of ADR 0382.

    Attributes:
        name: The bar, worded as the record words it.
        met: Whether it is met. There is no third value.
        detail: What was found, in words a person can check.
    """

    name: str
    met: bool
    detail: str


@dataclass(frozen=True)
class AgreementResult:
    """The seven bars, and every disagreement on the extended enumeration.

    Attributes:
        bars: One result per bar, in ADR 0382's order.
        disagreements: Every case where the two laws differ, each with a
            certificate. Omitting one fails bar 5.
    """

    bars: tuple[BarResult, ...]
    disagreements: tuple[Disagreement, ...]

    @property
    def met(self) -> bool:
        """Return whether every bar is met."""
        return all(bar.met for bar in self.bars)

    def bar(self, name: str) -> BarResult:
        """Return the named bar.

        Args:
            name: The bar's name, as `BAR_NAMES` spells it.

        Returns:
            That bar's result.

        Raises:
            KeyError: If no bar carries that name.
        """
        for bar in self.bars:
            if bar.name == name:
                return bar
        raise KeyError(name)


@dataclass(frozen=True)
class HandGuard:
    """The hand-written law's guard, as an equality at the release literal.

    Attributes:
        guard: A `DerivedGuard` whose form is equality.
        release: The release literal the equality names.
    """

    guard: DerivedGuard
    release: float


def hand_guard(release: float) -> HandGuard:
    """Return the hand guard as an equality at ``release``.

    The release value is read from the derived law's release literal, which
    itself was read from ``Configs.TAG_LIST``. Nothing here types ``3.0``.

    Args:
        release: The release literal the hand law equals.

    Returns:
        A hand guard whose form is equality.
    """
    return HandGuard(
        guard=DerivedGuard.equality(release, file=_HAND_GUARD_FILE, line=0),
        release=release,
    )


def enumerate_samples() -> tuple[ControllerSample, ...]:
    """Return every case ADR 0382 names, in a fixed product order.

    Five tank levels, three bottle levels, three belt positions, seven modes on
    each of the two mode tags, and both values of each valve. The product is
    exhaustive over that grid, not sampled. Seed `ENUMERATION_SEED` is recorded
    and not needed for ordering.

    Returns:
        The cases, in product order, which is deterministic.
    """
    levels = (LEVEL_MIN - 1.0, LEVEL_MIN, 5.0, LEVEL_MAX, LEVEL_MAX + 1.0)
    bottles = (BOTTLE_MAX - 1.0, BOTTLE_MAX, BOTTLE_MAX + 1.0)
    belts = (0.0, 1.0, 2.0)
    modes = ENUMERATION_MODES
    valves = (0.0, 1.0)
    found: list[ControllerSample] = []
    for level in levels:
        for bottle in bottles:
            for belt in belts:
                for input_mode in modes:
                    for output_mode in modes:
                        for input_valve in valves:
                            for output_valve in valves:
                                found.append(
                                    ControllerSample(
                                        at=_AT,
                                        level=level,
                                        level_min=LEVEL_MIN,
                                        level_max=LEVEL_MAX,
                                        input_valve=input_valve,
                                        input_mode=input_mode,
                                        bottle_level=bottle,
                                        bottle_max=BOTTLE_MAX,
                                        belt=belt,
                                        output_valve=output_valve,
                                        output_mode=output_mode,
                                    )
                                )
    return tuple(found)


def _literal_bar(law: DerivedValveLaw) -> BarResult:
    """Bar 1: the four constants, each quoting the source node."""
    wrong: list[str] = []
    seen: list[str] = []
    for name, want, text in _EXPECTED_LITERALS:
        try:
            literal = law.literal(name)
        except KeyError:
            wrong.append(f"{name} was not derived")
            continue
        seen.append(
            f"{name} {literal.value} written `{literal.literal_text}` "
            f"from {literal.file}:{literal.line}"
        )
        if literal.value != want:
            wrong.append(f"{name} is {literal.value}, the bar is {want}")
        if literal.literal_text != text:
            wrong.append(f"{name} quotes `{literal.literal_text}`, the source writes `{text}`")
        if literal.line <= 0:
            wrong.append(f"{name} carries no line")
    detail = "; ".join(seen) if not wrong else "; ".join(wrong)
    return BarResult(name=BAR_NAMES[0], met=not wrong, detail=detail)


def _comparison_bar(law: DerivedValveLaw) -> BarResult:
    """Bar 2: input and output comparisons match the source's order and sense."""
    wrong: list[str] = []
    try:
        input_rule = law.rule(Side.INPUT)
    except KeyError:
        wrong.append("no input rule was derived")
        input_rule = None
    if input_rule is not None:
        if len(input_rule.branches) != 2:
            wrong.append(f"input has {len(input_rule.branches)} branches, the bar is 2")
        else:
            first, second = input_rule.branches
            wrong.extend(
                _branch_wrong(first, "tank_level_value", ">", "tank_level_max", 0.0, "first")
            )
            wrong.extend(
                _branch_wrong(second, "tank_level_value", "<", "tank_level_min", 1.0, "second")
            )
        if input_rule.otherwise is not None:
            wrong.append(f"input otherwise is {input_rule.otherwise}, the bar is nothing required")
    try:
        output_rule = law.rule(Side.OUTPUT)
    except KeyError:
        wrong.append("no output rule was derived")
        output_rule = None
    if output_rule is not None:
        if len(output_rule.branches) != 1:
            wrong.append(f"output has {len(output_rule.branches)} branches, the bar is 1")
        else:
            branch = output_rule.branches[0]
            if len(branch.conditions) != 2:
                wrong.append(f"output has {len(branch.conditions)} conditions, the bar is 2")
            else:
                wrong.extend(
                    _condition_wrong(
                        branch.conditions[0],
                        "bottle_level_value",
                        ">",
                        "bottle_level_max",
                        None,
                    )
                )
                wrong.extend(
                    _condition_wrong(
                        branch.conditions[1],
                        "bottle_distance_to_filler_value",
                        ">",
                        None,
                        1.0,
                    )
                )
            if branch.writes != 0.0:
                wrong.append(f"output branch writes {branch.writes}, the bar is 0.0")
        if output_rule.otherwise != 1.0:
            wrong.append(f"output otherwise is {output_rule.otherwise}, the bar is 1.0")
    detail = (
        "above the maximum closes, below the minimum opens, the band is silence; "
        "full or past the filler closes, every other reading opens"
    )
    return BarResult(name=BAR_NAMES[1], met=not wrong, detail="; ".join(wrong) or detail)


def _branch_wrong(
    branch: DerivedBranch, left: str, operator: str, right: str, writes: float, which: str
) -> list[str]:
    """Return what is wrong with one single-condition branch."""
    if len(branch.conditions) != 1:
        return [f"the {which} branch has {len(branch.conditions)} conditions, the bar is 1"]
    wrong = _condition_wrong(branch.conditions[0], left, operator, right, None)
    if branch.writes != writes:
        wrong.append(f"the {which} branch writes {branch.writes}, the bar is {writes}")
    return wrong


def _condition_wrong(
    condition: DerivedCondition,
    left: str,
    operator: str,
    right_signal: str | None,
    right_literal: float | None,
) -> list[str]:
    """Return what is wrong with one derived comparison."""
    wrong: list[str] = []
    if condition.left != left:
        wrong.append(f"the left side is {condition.left}, the bar is {left}")
    if condition.operator != operator:
        wrong.append(f"the operator is {condition.operator}, the bar is {operator}")
    if condition.right_signal != right_signal:
        wrong.append(f"the right side is {condition.right_signal}, the bar is {right_signal}")
    if right_literal is not None and condition.right_literal != right_literal:
        wrong.append(f"the right literal is {condition.right_literal}, the bar is {right_literal}")
    return wrong


def guard_forms_meet_bar(derived: DerivedGuard, hand: DerivedGuard, *, release: float) -> BarResult:
    """Bar 3: each guard has the named form, and the two differ, by form.

    The check inspects ``form``. It does not try a hand-picked list of modes.
    A form that can hold only an exclusion list cannot represent the hand
    equality, so it cannot meet this bar.

    Args:
        derived: The derived guard (must be an exclusion).
        hand: The hand guard (must be an equality).
        release: The release literal the hand equality must name.

    Returns:
        Whether the bar is met, with a detail a person can check.
    """
    wrong: list[str] = []
    if derived.form is not GuardForm.EXCLUSION:
        wrong.append(f"the derived guard's form is {derived.form.value}, the bar is exclusion")
    if hand.form is not GuardForm.EQUALITY:
        wrong.append(f"the hand guard's form is {hand.form.value}, the bar is equality")
    if not derived.differs_in_form_from(hand):
        wrong.append("the two guards do not differ in form")
    if derived.states_only(release):
        wrong.append("the derived exclusion answered as if it were an equality")
    if not hand.states_only(release):
        wrong.append("the hand equality does not state only the release mode")
    if wrong:
        return BarResult(name=BAR_NAMES[2], met=False, detail="; ".join(wrong))
    named = ", ".join(str(mode) for mode in derived.manual_modes)
    return BarResult(
        name=BAR_NAMES[2],
        met=True,
        detail=(
            f"derived form is exclusion of {{{named}}}; "
            f"hand form is equality at {release}; forms differ"
        ),
    )


def _guard_form_bar(law: DerivedValveLaw, hand: HandGuard) -> BarResult:
    """Bar 3 for a derived law against the hand guard."""
    return guard_forms_meet_bar(law.guard, hand.guard, release=hand.release)


def _forced_writes_bar(law: DerivedValveLaw) -> BarResult:
    """Bar 4: forced actuator writes at modes 1 and 2 are a stated fact."""
    writes = law.forced_writes
    wrong: list[str] = []
    if len(writes) != len(_EXPECTED_FORCED):
        wrong.append(f"{len(writes)} forced writes, the bar is {len(_EXPECTED_FORCED)}")
    for index, (mode, value, text) in enumerate(_EXPECTED_FORCED):
        if index >= len(writes):
            wrong.append(f"forced write at mode {mode} is missing")
            continue
        write = writes[index]
        if write.mode != mode:
            wrong.append(f"forced write mode is {write.mode}, the bar is {mode}")
        if write.value != value:
            wrong.append(f"forced write at mode {mode} is {write.value}, the bar is {value}")
        if write.literal_text != text:
            wrong.append(
                f"forced write at mode {mode} quotes `{write.literal_text}`, "
                f"the source writes `{text}`"
            )
        if write.line <= 0:
            wrong.append(f"forced write at mode {mode} carries no line")
    if wrong:
        return BarResult(name=BAR_NAMES[3], met=False, detail="; ".join(wrong))
    detail = "; ".join(
        f"mode {write.mode} writes {write.value} "
        f"(`{write.literal_text}` at {write.file}:{write.line})"
        for write in writes
    )
    return BarResult(name=BAR_NAMES[3], met=True, detail=detail)


def _hand_stated(sample: ControllerSample, release: float) -> bool:
    """Return whether the hand law states the comparison for ``sample``."""
    return sample.input_mode == release and sample.output_mode == release


def _hand(sample: ControllerSample) -> tuple[Standing, tuple[str, ...], float | None, float | None]:
    """Return the hand law's standing, sentences, and required values."""
    report = assess_plant(register=_REGISTER, controller=sample)
    required_input: float | None = None
    required_output: float | None = None
    if report.broken or report.held:
        # Re-derive the required values the hand law used, for the certificate.
        if sample.level > sample.level_max:
            required_input = 0.0
        elif sample.level < sample.level_min:
            required_input = 1.0
        if sample.bottle_level > sample.bottle_max or sample.belt > 1.0:
            required_output = 0.0
        else:
            required_output = 1.0
    if report.broken:
        return (
            Standing.BROKEN,
            tuple(sorted(item.statement for item in report.broken)),
            required_input,
            required_output,
        )
    if report.held:
        return Standing.HELD, (), required_input, required_output
    return Standing.UNSTATED, (), None, None


def _derived(law: DerivedValveLaw, sample: ControllerSample) -> tuple[Standing, tuple[str, ...]]:
    """Return the derived law's standing and sentences for one sample."""
    if not law.stated(sample):
        return Standing.UNSTATED, ()
    found = certified_breaks(law, sample)
    if not found:
        return Standing.HELD, ()
    return Standing.BROKEN, tuple(sorted(item.law_break.statement for item in found))


def _required_text(value: float | None) -> str:
    """Render a required actuator value, or silence."""
    if value is None:
        return "silence"
    return plain(value)


def _list_disagreements(law: DerivedValveLaw, hand: HandGuard) -> tuple[Disagreement, ...]:
    """Return every case where the two laws differ on standing or value."""
    found: list[Disagreement] = []
    for sample in enumerate_samples():
        hand_stated = _hand_stated(sample, hand.release)
        derived_stated = law.stated(sample)
        if hand_stated != derived_stated:
            comparison = (
                f"derived states={derived_stated}, hand states={hand_stated} "
                f"at modes {plain(sample.input_mode)} and {plain(sample.output_mode)}"
            )
            found.append(
                Disagreement(
                    sample=sample,
                    kind="stated",
                    side=None,
                    derived_stated=derived_stated,
                    hand_stated=hand_stated,
                    derived_required=None,
                    hand_required=None,
                    certificate=disagreement_certificate(
                        law_name=CONTROLLER_VALVE.name,
                        sample=sample,
                        comparison=comparison,
                        kind="stated",
                    ),
                )
            )
            continue
        if not derived_stated:
            # Agreement in silence: both unstated. Not a disagreement.
            continue
        hand_standing, hand_statements, hand_in, hand_out = _hand(sample)
        derived_standing, derived_statements = _derived(law, sample)
        if hand_standing is derived_standing and hand_statements == derived_statements:
            continue
        # Differ on the required actuator value on at least one side.
        for side in Side:
            derived_required = law.required(sample, side)
            hand_required = hand_in if side is Side.INPUT else hand_out
            if derived_required == hand_required:
                continue
            comparison = (
                f"{side.value}: derived requires {_required_text(derived_required)}, "
                f"hand requires {_required_text(hand_required)}"
            )
            found.append(
                Disagreement(
                    sample=sample,
                    kind="actuator",
                    side=side.value,
                    derived_stated=True,
                    hand_stated=True,
                    derived_required=derived_required,
                    hand_required=hand_required,
                    certificate=disagreement_certificate(
                        law_name=CONTROLLER_VALVE.name,
                        sample=sample,
                        comparison=comparison,
                        kind="actuator",
                        side=side.value,
                    ),
                )
            )
    return tuple(found)


def _enumeration_bar(
    law: DerivedValveLaw, hand: HandGuard
) -> tuple[BarResult, tuple[Disagreement, ...]]:
    """Bar 5: every disagreement on the extended enumeration is listed."""
    samples = enumerate_samples()
    modes_in = {sample.input_mode for sample in samples}
    modes_out = {sample.output_mode for sample in samples}
    wrong: list[str] = []
    if len(samples) != EXPECTED_CASE_COUNT:
        wrong.append(f"{len(samples)} cases, the bar is {EXPECTED_CASE_COUNT}")
    if modes_in != set(ENUMERATION_MODES) or modes_out != set(ENUMERATION_MODES):
        wrong.append(f"mode set is {sorted(modes_in)}, the bar is {list(ENUMERATION_MODES)}")
    disagreements = _list_disagreements(law, hand)
    if not disagreements:
        wrong.append("the disagreement list is empty, which edits either law would cause")
    if wrong:
        return (
            BarResult(name=BAR_NAMES[4], met=False, detail="; ".join(wrong)),
            disagreements,
        )
    return (
        BarResult(
            name=BAR_NAMES[4],
            met=True,
            detail=(
                f"{len(samples)} cases on modes {list(ENUMERATION_MODES)}; "
                f"{len(disagreements)} disagreements listed, each with a certificate"
            ),
        ),
        disagreements,
    )


def _certificate_bar(law: DerivedValveLaw, disagreements: tuple[Disagreement, ...]) -> BarResult:
    """Bar 6: certificate shape, and page admission unchanged."""
    wrong: list[str] = []
    for kind in (LawCertificate, CertificateRow, Disagreement):
        for field in dataclasses.fields(kind):
            folded = field.name.casefold()
            for word in _SCORE_WORDS:
                if word in folded:
                    wrong.append(f"{kind.__name__}.{field.name} could hold a {word}")
    if issubclass(LawCertificate, LawBreak):
        wrong.append("a certificate is a LawBreak subclass")
    if issubclass(Disagreement, LawBreak):
        wrong.append("a disagreement is a LawBreak subclass")
    checked = 0
    for sample in enumerate_samples()[:200]:
        for certified in certified_breaks(law, sample):
            checked += 1
            if type(certified.law_break) is not LawBreak:
                wrong.append("a break is not exactly a LawBreak")
            if law_page([certified.law_break], register=_REGISTER) != (certified.law_break,):
                wrong.append("a break was not admitted to the page")
            certificate = certified.certificate
            if not certificate.rows:
                wrong.append("a certificate names no rows")
            if not certificate.comparison:
                wrong.append("a certificate shows no comparison")
            for text in (certificate.statement, certificate.comparison):
                for word in _SCORE_WORDS:
                    if word in text.casefold():
                        wrong.append(f"a certificate sentence carries {word}")
    for disagreement in disagreements[:50]:
        checked += 1
        certificate = disagreement.certificate
        if not certificate.rows:
            wrong.append("a disagreement certificate names no rows")
        if not certificate.comparison:
            wrong.append("a disagreement certificate shows no comparison")
        for text in (certificate.statement, certificate.comparison):
            for word in _SCORE_WORDS:
                if word in text.casefold():
                    wrong.append(f"a disagreement certificate carries {word}")
        if type(certificate) is not LawCertificate:
            wrong.append("a disagreement certificate is not a LawCertificate")
    detail = f"{checked} certificates checked, each naming its rows and its false comparison"
    return BarResult(name=BAR_NAMES[5], met=not wrong, detail="; ".join(wrong) or detail)


def check_agreement(law: DerivedValveLaw) -> AgreementResult:
    """Return ADR 0382's seven bars for ``law``.

    Args:
        law: The derived law.

    Returns:
        One result per bar, in the record's order, and every disagreement on
        the extended enumeration. Bar 7 is reported as not computed.
    """
    try:
        release = law.literal("release_mode").value
    except KeyError:
        release = float("nan")
    hand = hand_guard(release)
    enumeration, disagreements = _enumeration_bar(law, hand)
    return AgreementResult(
        bars=(
            _literal_bar(law),
            _comparison_bar(law),
            _guard_form_bar(law, hand),
            _forced_writes_bar(law),
            enumeration,
            _certificate_bar(law, disagreements),
            BarResult(
                name=BAR_NAMES[6],
                met=False,
                detail=(
                    "not computed here: the suite, mypy --strict src, ruff and an empty "
                    "diff on declared_law.py are reported by the session that runs them"
                ),
            ),
        ),
        disagreements=disagreements,
    )
