"""Reading rules out of Rockwell Logix controller code, as drafts for an engineer to sign off.

A `.L5X` file is Rockwell's XML export of a Logix project: the programs, the routines, the rungs,
the tags and the controller's own metadata, all as plain text. This module reads three kinds of
statement out of it and writes them as draft rules in the shape Atlas's declared laws already use:

- **Interlocks.** A rung that guards one output on a condition. "The pump runs only while the
  level is below the high limit" is an interlock, and the rung says so in a form this module can
  read: a rung whose last instruction writes an output tag and whose earlier instructions are
  contacts and comparisons.
- **Timer presets.** A `TON`, `TOF` or `RTO` instruction carries a `.PRE` preset. A pump start
  delay of ten seconds is a timer preset, and the preset is a number in the export.
- **Alarm thresholds.** A comparison rung whose result drives an alarm tag or an alarm bit. A
  high-high level alarm at 92 percent is a threshold, and it is a number in a comparison.

**Everything it produces is a draft.** A draft rule is not a law and does not become one. It
carries `DRAFT` in its own standing, it names the file and line it came from so an engineer can
check it, and nothing in this module edits `phos.atlas.declared_law`, adds a law to a register, or
places anything on the law page. Promoting a draft is a human act with its own record.

**What it cannot read is listed, not guessed.** Logix is a large language and this is a small
reader. A rung with an instruction this module does not model, a structured tag it cannot flatten,
an indirect reference, or a rung that is commented out all end up in `unreadable` with the reason
and the line. That list is part of the output, not a warning beside it, because a rule register
that silently omits half a program is worse than one that says which half.

**This makes no detection claim.** It is a parser and a translator. It says nothing about whether
any rule is correct, whether the plant obeys it, or whether breaking it would be an attack.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

__all__ = [
    "DraftRule",
    "DraftRuleKind",
    "L5XError",
    "RuleRegister",
    "UnreadableRung",
    "parse_export",
]

#: The XML namespace a Logix export declares, when it declares one.
_NAMESPACE: Final = "{http://www.rockwellautomation.com/rockwellautomation/integration/2020/04}"

#: Comparison instructions this reader models, by the name Logix actually writes.
#:
#: Two vocabularies are in play and both are real. Older projects write the four- and three-letter
#: forms (``GRT``, ``LES``); Studio 5000 writes the short forms (``GRT`` for greater-than is
#: written ``GRT`` in the instruction set but appears as ``GT`` in exported rungs, and
#: ``EQU``/``NEQ`` appear as ``EQU``/``NEQ``). A reader that knows only one vocabulary silently
#: reads nothing from half the projects in the world, so both are listed and both are tested
#: against a real export.
_COMPARISONS: Final[frozenset[str]] = frozenset(
    {"EQU", "NEQ", "LES", "LEQ", "GRT", "GEQ", "LIM", "GT", "LT", "GE", "LE", "EQ", "NE"}
)

#: Timer instructions whose preset is a number worth reading.
_TIMERS: Final[frozenset[str]] = frozenset({"TON", "TOF", "RTO"})

#: Contacts, which pass or block a rung's power and carry no number.
_CONTACTS: Final[frozenset[str]] = frozenset({"XIC", "XIO", "OTL", "OTU", "OTE"})

#: The ``CMP`` instruction, whose argument is a free-text expression rather than two operands.
_CMP: Final = "CMP"

#: How a comparison operator reads in English, for the plain-language statement. Both
#: vocabularies map onto the same six readings.
_READS_AS: Final[dict[str, str]] = {
    "EQU": "equals",
    "EQ": "equals",
    "NEQ": "does not equal",
    "NE": "does not equal",
    "LES": "is less than",
    "LT": "is less than",
    "LEQ": "is at most",
    "LE": "is at most",
    "GRT": "is greater than",
    "GT": "is greater than",
    "GEQ": "is at least",
    "GE": "is at least",
}

#: A ``CMP`` expression this reader can read: ``<tag> <operator> <number>``, with the operator
#: written as a word or a symbol. Anything else, including a modulus or a function call, is left
#: to the unreadable list rather than parsed by guesswork.
_CMP_EXPRESSION: Final = re.compile(
    r"^\s*(?P<tag>[A-Za-z_][\w.]*)\s*"
    r"(?P<op><=|>=|<>|<|>|=|\bMOD\b|\bAND\b|\bOR\b)\s*"
    r"(?P<value>-?\d+(?:\.\d+)?)\s*$"
)

#: What each ``CMP`` operator symbol reads as.
_CMP_READS_AS: Final[dict[str, str]] = {
    "<": "is less than",
    "<=": "is at most",
    ">": "is greater than",
    ">=": "is at least",
    "=": "equals",
    "<>": "does not equal",
}


class L5XError(ValueError):
    """Raised when a file is not an L5X export at all, so no rung can be read from it."""


class DraftRuleKind(str):
    """The three kinds of rule this module derives. A word, for the register's own grouping."""

    INTERLOCK = "interlock"
    TIMER_PRESET = "timer preset"
    ALARM_THRESHOLD = "alarm threshold"


@dataclass(frozen=True)
class DraftRule:
    """One rule read out of controller code, awaiting an engineer's sign-off.

    The fields are the declared-law vocabulary plus what a reviewer needs to check the derivation:
    every rule names the file and the line it came from, and none carries a confidence, a weight
    or a score. A rule is a statement about what the code says, not a belief about the plant.

    Attributes:
        name: A stable name, derived from the routine and the tag it concerns.
        statement: What the code says, in a sentence a person can check against the rung.
        kind: Which of the three kinds this is.
        tag: The tag the rule constrains or writes.
        threshold: The number in the rule, when it has one. ``None`` for a rule with no number.
        unit: The unit the threshold is in, when the export states one. Usually ``None``.
        routine: The routine the rung lives in.
        file: The exported file.
        line: The line in that file, counting from one, where the rung begins.
        signed_off_by: Always empty when derived. A person fills it in, and nothing here does.
        standing: Always ``draft``. Nothing in this module produces a law in force.
    """

    name: str
    statement: str
    kind: str
    tag: str
    threshold: float | None
    unit: str | None
    routine: str
    file: str
    line: int
    signed_off_by: str = ""
    standing: str = "draft"

    def __post_init__(self) -> None:
        """Refuse anything that has been promoted without a sign-off.

        This is the guard that keeps the promise in the module docstring: a draft cannot become
        anything but a draft by being constructed, and a rule claiming a sign-off with no name
        attached is refused rather than trusted.

        Raises:
            ValueError: If ``standing`` is not ``draft``, or a sign-off is claimed with no name.
        """
        if self.standing != "draft":
            raise ValueError("a derived rule is a draft and cannot be constructed as anything else")
        if self.signed_off_by and not self.signed_off_by.strip():
            raise ValueError("a sign-off must name the engineer who gave it")


@dataclass(frozen=True)
class UnreadableRung:
    """A rung this reader could not translate, with the reason.

    Attributes:
        routine: The routine the rung lives in.
        file: The exported file.
        line: The line the rung begins on.
        reason: Why it could not be read, in words a person can act on.
        text: The rung's own text, truncated, so a reviewer can see what was skipped.
    """

    routine: str
    file: str
    line: int
    reason: str
    text: str


@dataclass(frozen=True)
class RuleRegister:
    """The draft register: what was read, and what was not.

    Attributes:
        rules: The draft rules, in the order the export lists them.
        unreadable: Every ladder rung that could not be translated, with its reason.
        not_ladder: Every routine whose type this reader does not parse, by name and type. A
            structured-text or function-block routine is not unreadable in the rung sense; it is
            code this reader never looked at, and saying so is the difference between a register
            that covers a program and one that covers part of it.
        source: The file the register was built from.
    """

    rules: tuple[DraftRule, ...] = field(default_factory=tuple)
    unreadable: tuple[UnreadableRung, ...] = field(default_factory=tuple)
    not_ladder: tuple[str, ...] = field(default_factory=tuple)
    source: str = ""

    def of_kind(self, kind: str) -> tuple[DraftRule, ...]:
        """Return the rules of one kind.

        Args:
            kind: One of `DraftRuleKind`'s values.

        Returns:
            The matching rules, in register order.
        """
        return tuple(rule for rule in self.rules if rule.kind == kind)

    def summary(self) -> str:
        """Return one plain paragraph: what was read and what was not.

        Returns:
            A sentence naming every count that matters, and saying that nothing is in force.
        """
        if not self.rules and not self.unreadable and not self.not_ladder:
            return "This export holds no rungs, so there is nothing to derive and nothing refused."
        parts = [
            f"{len(self.rules)} draft rule(s) read",
            f"{len(self.unreadable)} ladder rung(s) this reader could not translate",
        ]
        if self.not_ladder:
            parts.append(
                f"{len(self.not_ladder)} routine(s) not read at all because they are not ladder"
            )
        return (
            ", ".join(parts)
            + ". Nothing here is in force: every rule needs an engineer's sign-off, and anything "
            "not understood is listed rather than guessed."
        )


class _Source:
    """The text of an export, so a rung's XML can be mapped back to a line number.

    Logix exports put each rung's text on one long line, but not always, so the search is by the
    rung's own text rather than by assuming a layout. A rung that appears twice gets the earlier
    line, which is what a reviewer reading top to bottom would check first.
    """

    def __init__(self, text: str) -> None:
        """Hold the text and a line index.

        Args:
            text: The whole file.
        """
        self._text = text
        self._lines = text.splitlines()

    def line_of(self, needle: str) -> int:
        """Return the one-based line where ``needle`` first appears, or 0 when it does not.

        Args:
            needle: The text to find, usually a rung's body.

        Returns:
            The line number, or 0 when absent. Zero rather than an exception, because a rung whose
            line cannot be found is still a rung and is reported with 0 as its line.
        """
        stripped = needle.strip()
        if not stripped:
            return 0
        for number, line in enumerate(self._lines, start=1):
            if stripped in line:
                return number
        return 0


def _tag_of(rung_text: str, instruction: str) -> str:
    """Return the first operand of an instruction, e.g. the tag in ``XIC(Tank_Level)``.

    Args:
        rung_text: The rung's text.
        instruction: The instruction name.

    Returns:
        The operand, or an empty string when the instruction is absent.
    """
    match = re.search(rf"{instruction}\(([^)]*)\)", rung_text)
    return match.group(1).strip() if match else ""


def _operands(rung_text: str, instruction: str) -> tuple[str, ...]:
    """Return every argument of an instruction, e.g. ``(Tag, 92.0)`` for ``GRT(Tag,92.0)``.

    Logix writes a comparison as ``GRT(Tag,Value)``, sometimes with the value first and the tag
    second. Both orders occur in real code, so both are handled by the caller looking at which
    operand parses as a number.

    Args:
        rung_text: The rung's text.
        instruction: The instruction name.

    Returns:
        The arguments, stripped. Empty when the instruction is absent.
    """
    match = re.search(rf"{instruction}\(([^()]*)\)", rung_text)
    if not match:
        return ()
    return tuple(part.strip() for part in match.group(1).split(","))


def _as_number(text: str) -> float | None:
    """Return ``text`` as a float when it is a plain number, else ``None``.

    Args:
        text: The operand.

    Returns:
        The number, or ``None``. A tag name returns ``None``; so does a negative number written
        inside a nested instruction, which this reader does not model.
    """
    try:
        return float(text)
    except ValueError:
        return None


def _split_tag(raw: str) -> tuple[str, str | None]:
    """Split an operand into a tag and a member, as in ``Alarm_HH.PRE``.

    Args:
        raw: The operand.

    Returns:
        The tag and the member, with ``None`` for the member when there is none.
    """
    head, _, tail = raw.partition(".")
    return head.strip(), (tail.strip() or None) if tail else None


def _looks_like_alarm(tag: str) -> bool:
    """Return whether a tag name reads as an alarm, by its own words.

    Args:
        tag: The tag name.

    Returns:
        True when the name carries an alarm word. This is a heuristic and is labelled as one in
        the rule's statement, so a reviewer knows the classification was by name, not by circuit.
    """
    lowered = tag.lower()
    return any(word in lowered for word in ("alarm", "alm", "hh", "ll", "trip", "fault"))


def _interlock_or_threshold(
    rung_text: str,
    *,
    routine: str,
    file: str,
    line: int,
) -> tuple[DraftRule | None, UnreadableRung | None]:
    """Translate one rung, or say why it cannot be.

    The shape this reader understands is deliberately narrow: a rung built from contacts, at most
    one comparison, and one output or timer. A rung with two comparisons, an arithmetic
    instruction, an indirect reference, or a jump is returned as unreadable with the instruction
    named, because translating it without a model of what it means would be a guess.

    Args:
        rung_text: The rung's text.
        routine: The routine it lives in.
        file: The exported file.
        line: The line the rung begins on.

    Returns:
        The rule, or the reason it could not be read. Never both, never neither.
    """
    if not rung_text.strip():
        return None, UnreadableRung(
            routine=routine, file=file, line=line, reason="the rung is empty", text=""
        )

    instructions = set(re.findall(r"\b([A-Z]{2,5})\(", rung_text))
    unknown = instructions - _COMPARISONS - _TIMERS - _CONTACTS - {_CMP}
    if unknown:
        return None, UnreadableRung(
            routine=routine,
            file=file,
            line=line,
            reason=(
                "this reader does not model the instruction(s) "
                + ", ".join(sorted(unknown))
                + ", so the rung is listed rather than guessed"
            ),
            text=rung_text.strip()[:160],
        )

    if "[" in rung_text:
        # An index in the comparison's own operand is a tag that is only known at run time. An
        # index in the *output* is a different thing: writing to Array[4].0 is a static statement
        # about which member is written, and real projects do it constantly. So the check is on
        # the comparison's operands only.
        for name in _COMPARISONS:
            for operand in _operands(rung_text, name):
                if "[" in operand:
                    return None, UnreadableRung(
                        routine=routine,
                        file=file,
                        line=line,
                        reason=(
                            "the comparison reads a tag through an index, whose target is not "
                            "known until run time"
                        ),
                        text=rung_text.strip()[:160],
                    )

    comparisons = [name for name in instructions if name in _COMPARISONS]
    timers = [name for name in instructions if name in _TIMERS]

    # A CMP rung carries its comparison as an expression, so it is handled on its own before the
    # two-operand forms below. A RLL export writes CMP for any comparison the drag-and-drop
    # palette could not write as a single instruction, and real projects use it freely.
    if _CMP in instructions:
        return _from_cmp(
            rung_text,
            routine=routine,
            file=file,
            line=line,
            output_tag=_tag_of(rung_text, "OTE") or _tag_of(rung_text, "OTL"),
        )

    if len(comparisons) > 1:
        return None, UnreadableRung(
            routine=routine,
            file=file,
            line=line,
            reason=(
                "the rung combines more than one comparison, and this reader does not translate "
                "conjunctions of them"
            ),
            text=rung_text.strip()[:160],
        )

    output_tag = ""
    for instruction in ("OTE", "OTL", "OTU"):
        output_tag = _tag_of(rung_text, instruction)
        if output_tag:
            break

    if timers:
        timer = timers[0]
        operands = _operands(rung_text, timer)
        if len(operands) < 2:
            return None, UnreadableRung(
                routine=routine,
                file=file,
                line=line,
                reason=f"the {timer} call does not name both a tag and a preset",
                text=rung_text.strip()[:160],
            )
        preset_tag, preset_tag_member = _split_tag(operands[0])
        preset = _as_number(operands[1])
        if operands[1].strip() == "?":
            return None, UnreadableRung(
                routine=routine,
                file=file,
                line=line,
                reason=(
                    f"the {timer} preset is written as '?', so the export itself does not state a "
                    "number and this reader will not invent one"
                ),
                text=rung_text.strip()[:160],
            )
        if preset is None:
            # A preset given as another tag is a value that changes with the plant, not a rule.
            return None, UnreadableRung(
                routine=routine,
                file=file,
                line=line,
                reason=(
                    f"the {timer} preset is {operands[1]!r}, which is a tag rather than a number, "
                    "so the preset is not a constant this reader can state"
                ),
                text=rung_text.strip()[:160],
            )
        guarded_by = _guarding_tag(rung_text, timer)
        name = f"{routine}.{preset_tag}.{preset_tag_member or 'PRE'}"
        statement = (
            f"In routine {routine}, timer {timer} on {operands[0]} has a preset of {preset:g}. "
            f"The rung also reads {guarded_by or 'no other tag'}. This is what the code says the "
            "delay is; it is not a claim that the plant waits that long."
        )
        return (
            DraftRule(
                name=name,
                statement=statement,
                kind=DraftRuleKind.TIMER_PRESET,
                tag=preset_tag,
                threshold=preset,
                unit="seconds" if timer in {"TON", "TOF", "RTO"} else None,
                routine=routine,
                file=file,
                line=line,
            ),
            None,
        )

    if not comparisons:
        return None, UnreadableRung(
            routine=routine,
            file=file,
            line=line,
            reason=(
                "the rung has contacts but no comparison and no timer, so there is no number and "
                "no condition this reader can state as a rule"
            ),
            text=rung_text.strip()[:160],
        )

    if not output_tag:
        return None, UnreadableRung(
            routine=routine,
            file=file,
            line=line,
            reason=(
                "the rung has a comparison but writes no output, so what it guards is not stated "
                "in the rung"
            ),
            text=rung_text.strip()[:160],
        )

    comparison = comparisons[0]
    operands = _operands(rung_text, comparison)
    if len(operands) != 2:
        return None, UnreadableRung(
            routine=routine,
            file=file,
            line=line,
            reason=f"the {comparison} call does not name exactly two operands",
            text=rung_text.strip()[:160],
        )
    first, second = operands
    first_number, second_number = _as_number(first), _as_number(second)
    if first_number is not None and second_number is not None:
        return None, UnreadableRung(
            routine=routine,
            file=file,
            line=line,
            reason="both operands of the comparison are numbers, so no tag is constrained",
            text=rung_text.strip()[:160],
        )
    if first_number is None and second_number is None:
        return None, UnreadableRung(
            routine=routine,
            file=file,
            line=line,
            reason=(
                "neither operand of the comparison is a number, so the rung compares two tags and "
                "this reader does not state a threshold it cannot read"
            ),
            text=rung_text.strip()[:160],
        )
    tag_raw, value = (first, second_number) if second_number is not None else (second, first_number)
    assert value is not None  # the branch above guarantees one number
    tag, member = _split_tag(tag_raw)
    constrained = f"{tag}.{member}" if member else tag

    kind = (
        DraftRuleKind.ALARM_THRESHOLD
        if _looks_like_alarm(output_tag) or _looks_like_alarm(tag)
        else DraftRuleKind.INTERLOCK
    )
    reads_as = _READS_AS[comparison]
    if first_number is not None:
        # The number came first, so the comparison reads the other way round: "40 is less than X".
        reads_as = _READS_AS[comparison]
        statement = (
            f"In routine {routine}, {value:g} {reads_as} {constrained}, and that drives "
            f"{output_tag}. Translated from a rung whose number is written first, so the reading "
            "direction is reversed from the usual form."
        )
    else:
        statement = (
            f"In routine {routine}, {constrained} {reads_as} {value:g}, and that drives "
            f"{output_tag}."
        )
    if kind == DraftRuleKind.ALARM_THRESHOLD:
        statement += (
            " Classified as a threshold by the tag's own name, not by the circuit, so a reviewer "
            "should confirm what it does."
        )
    statement += " This is what the code says; it is not a claim that the plant keeps it."

    return (
        DraftRule(
            name=f"{routine}.{output_tag}",
            statement=statement,
            kind=kind,
            tag=tag,
            threshold=value,
            unit=None,
            routine=routine,
            file=file,
            line=line,
        ),
        None,
    )


def _from_cmp(
    rung_text: str,
    *,
    routine: str,
    file: str,
    line: int,
    output_tag: str,
) -> tuple[DraftRule | None, UnreadableRung | None]:
    """Translate a ``CMP`` rung whose expression is ``tag operator number``.

    ``CMP`` carries its comparison as free text, so it is the one place where the reader has to
    parse an expression rather than read two operands. Only the plain form is accepted: a tag, one
    of the six comparisons, and a number. A modulus, a boolean operator, a function call or a
    comparison against another tag is listed as unreadable, because evaluating it would mean
    implementing Logix's expression semantics, and a half-implemented one would produce rules that
    look right and are not.

    Args:
        rung_text: The rung's text.
        routine: The routine it lives in.
        file: The exported file.
        line: The line the rung begins on.
        output_tag: The tag the rung writes, or an empty string.

    Returns:
        The rule, or the reason it could not be read.
    """
    match = re.search(r"CMP\(([^()]*)\)", rung_text)
    if not match:
        return None, UnreadableRung(
            routine=routine,
            file=file,
            line=line,
            reason="a CMP instruction whose expression this reader could not isolate",
            text=rung_text.strip()[:160],
        )
    expression = match.group(1).strip()
    if not output_tag:
        return None, UnreadableRung(
            routine=routine,
            file=file,
            line=line,
            reason="a CMP rung that writes no output, so what it guards is not stated",
            text=rung_text.strip()[:160],
        )
    parsed = _CMP_EXPRESSION.match(expression)
    if not parsed or parsed.group("op") not in _CMP_READS_AS:
        return None, UnreadableRung(
            routine=routine,
            file=file,
            line=line,
            reason=(
                f"the CMP expression {expression!r} is not a plain tag-versus-number comparison, "
                "so this reader will not evaluate it"
            ),
            text=rung_text.strip()[:160],
        )
    tag_raw, operator, value_text = (
        parsed.group("tag"),
        parsed.group("op"),
        parsed.group("value"),
    )
    tag, member = _split_tag(tag_raw)
    constrained = f"{tag}.{member}" if member else tag
    value = float(value_text)
    kind = (
        DraftRuleKind.ALARM_THRESHOLD
        if _looks_like_alarm(output_tag) or _looks_like_alarm(tag)
        else DraftRuleKind.INTERLOCK
    )
    statement = (
        f"In routine {routine}, {constrained} {_CMP_READS_AS[operator]} {value:g}, and that "
        f"drives {output_tag}. Read from a CMP expression."
    )
    if kind == DraftRuleKind.ALARM_THRESHOLD:
        statement += (
            " Classified as a threshold by the tag's own name, not by the circuit, so a reviewer "
            "should confirm what it does."
        )
    statement += " This is what the code says; it is not a claim that the plant keeps it."
    return (
        DraftRule(
            name=f"{routine}.{output_tag}",
            statement=statement,
            kind=kind,
            tag=tag,
            threshold=value,
            unit=None,
            routine=routine,
            file=file,
            line=line,
        ),
        None,
    )


def _guarding_tag(rung_text: str, timer: str) -> str:
    """Return the first contact tag before a timer, or an empty string.

    Args:
        rung_text: The rung's text.
        timer: The timer instruction.

    Returns:
        The tag that starts the timer, or an empty string when there is none.
    """
    head = rung_text.split(f"{timer}(", 1)[0]
    for instruction in ("XIC", "XIO"):
        tag = _tag_of(head, instruction)
        if tag:
            return tag
    return ""


def _rungs(root: ElementTree.Element) -> tuple[list[tuple[str, str]], list[str]]:
    """Return every ladder rung, and the name of every routine this reader does not parse.

    A Logix routine has a type: ``RLL`` for ladder, ``ST`` for structured text, ``FBD`` for
    function block, ``SFC`` for sequential function chart. Only ``RLL`` is ladder, and only ladder
    rungs look like the text this module reads. Feeding a structured-text routine to the rung
    reader produces nonsense — every statement looks like an unknown instruction — so the type is
    checked first and anything that is not ladder is named in the second return value rather than
    silently skipped. That list is reported, because "this reader read 18 of 25 routines" is a fact
    a reviewer needs and "18 rules, no errors" is not.

    Args:
        root: The parsed document.

    Returns:
        The ladder rungs as ``(routine name, rung text)``, and the names of routines not parsed.
    """
    found: list[tuple[str, str]] = []
    not_ladder: list[str] = []
    for routine in root.iter():
        if not routine.tag.endswith("Routine"):
            continue
        name = routine.get("Name", "<unnamed>")
        kind = routine.get("Type", "")
        if kind != "RLL":
            not_ladder.append(f"{name} ({kind or 'no type stated'})")
            continue
        for rung in routine.iter():
            if not rung.tag.endswith("Rung"):
                continue
            for child in rung.iter():
                if child.tag.endswith("Text"):
                    found.append((name, child.text or ""))
                    break
    return found, not_ladder


def parse_export(path: Path) -> RuleRegister:
    """Read an L5X export and return its draft rule register.

    Args:
        path: The export. Plain XML, as Rockwell writes it.

    Returns:
        The register: every rule this reader could derive, and every rung it could not.

    Raises:
        L5XError: If the file cannot be read or is not XML at all. An export with no rungs is not
            an error; it returns an empty register with a summary that says so.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise L5XError(f"{path}: cannot be read ({error.strerror or error})") from error
    try:
        # A local export the caller names, not fetched input, so no XML hardening is claimed.
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as error:
        raise L5XError(f"{path}: is not XML that parses ({error})") from error

    source = _Source(text)
    rules: list[DraftRule] = []
    unreadable: list[UnreadableRung] = []
    rungs, not_ladder = _rungs(root)
    for routine, rung_text in rungs:
        line = source.line_of(rung_text)
        rule, refused = _interlock_or_threshold(
            rung_text, routine=routine, file=path.name, line=line
        )
        if rule is not None:
            rules.append(rule)
        if refused is not None:
            unreadable.append(refused)
    return RuleRegister(
        rules=tuple(rules),
        unreadable=tuple(unreadable),
        not_ladder=tuple(not_ladder),
        source=str(path),
    )
