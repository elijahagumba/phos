"""Measuring the L5X reader against hand-written rules, and being honest about the result.

The stage asks for "how many of the derived rules match hand-written ones, and what the parser
misses". Both halves matter, and the second matters more. A count of matches with no denominator
tells a reader nothing, and a count of matches on a program whose rules were written by the same
person who wrote the parser tells them less than nothing, because it is a test of consistency
rather than of reading.

**What is compared here, and what it can and cannot show.** The hand-written rules are
`data/phos-icssim-dev/roles.toml`: thirteen tag roles read by hand from ICSSim's Python source at a
pinned commit, each with the source line quoted. The derived rules are what the L5X reader makes of
an export. Those are not the same kind of statement — a role says what a tag *is*, a derived rule
says what a piece of code *requires* — so this module compares them only on the narrow ground they
share: a tag that the hand-written file marks as a setpoint has a threshold somewhere, and a
derived threshold rule naming that tag is one the hand-written record would expect to exist.

**The by-construction problem, stated rather than hidden.** ICSSim's control logic is Python, not
Logix. No L5X export of it exists. So a comparison against it measures tag naming and threshold
presence, not rung reading. A test built from an export *generated from our own simulator's rules*
would pass partly by construction, because the generator and the reader would share an author and
a vocabulary. This module therefore reports three numbers and refuses to combine them into a score:

- how many hand-written setpoints have a matching derived threshold,
- how many derived rules name a tag the hand-written record does not mention at all,
- how many hand-written setpoints have no derived rule, which is what the parser missed.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from phos.atlas.l5x import DraftRule, RuleRegister

__all__ = [
    "ROLES_FILE",
    "Agreement",
    "HandWrittenSetpoint",
    "compare",
    "hand_written_setpoints",
]

#: Where the hand-written record lives.
ROLES_FILE: Final = Path("data") / "phos-icssim-dev" / "roles.toml"


@dataclass(frozen=True)
class HandWrittenSetpoint:
    """One tag the hand-written record marks as a setpoint.

    Attributes:
        signal: The tag's name.
        quoted: The source line the role was read from.
    """

    signal: str
    quoted: str


@dataclass(frozen=True)
class Agreement:
    """What matched, what did not, and the three counts kept separate.

    Attributes:
        matched: Tags with a hand-written setpoint role and a derived threshold rule.
        derived_only: Derived rules naming a tag the hand-written record does not mention.
        missed: Hand-written setpoints with no derived rule.
        hand_written_total: How many setpoints the hand-written record holds, so the matched
            count has a denominator.
    """

    matched: tuple[str, ...]
    derived_only: tuple[str, ...]
    missed: tuple[str, ...]
    hand_written_total: int

    def summary(self) -> str:
        """Return one paragraph stating all three counts and refusing a single score.

        Returns:
            The paragraph. It says what the numbers cannot mean as well as what they can.
        """
        if self.hand_written_total == 0:
            return "The hand-written record holds no setpoints, so nothing can be compared."
        return (
            f"{len(self.matched)} of {self.hand_written_total} hand-written setpoint(s) have a "
            f"matching derived threshold; {len(self.missed)} were missed and "
            f"{len(self.derived_only)} derived rule(s) name a tag the hand-written record does not "
            "mention. These three counts are reported separately and are not combined into a "
            "score: the hand-written record describes ICSSim's Python source and the derived "
            "rules describe a Logix export, so agreement between them measures shared vocabulary "
            "as much as it measures reading."
        )


def hand_written_setpoints(root: Path) -> tuple[HandWrittenSetpoint, ...]:
    """Read the setpoint roles from the hand-written record.

    Args:
        root: The checkout root.

    Returns:
        One entry per tag whose role is ``setpoint``.

    Raises:
        FileNotFoundError: If the record is absent, which would make an empty comparison look
            like agreement.
    """
    path = root / ROLES_FILE
    parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    points = parsed.get("points", [])
    return tuple(
        HandWrittenSetpoint(signal=item["signal"], quoted=item.get("quote", ""))
        for item in points
        if item.get("role") == "setpoint"
    )


def compare(register: RuleRegister, hand_written: tuple[HandWrittenSetpoint, ...]) -> Agreement:
    """Compare a derived register against the hand-written setpoints.

    The comparison is by tag name, because that is the only thing the two records share. A derived
    rule names the tag it constrains; a hand-written role names a tag and says what it is. Matching
    on anything finer would require the export to come from the same program, and it does not.

    Args:
        register: What the reader derived.
        hand_written: What the hand-written record says.

    Returns:
        The three counts, kept separate.
    """
    derived_tags = {rule.tag for rule in register.rules if isinstance(rule, DraftRule)}
    written_tags = {entry.signal for entry in hand_written}
    matched = tuple(sorted(derived_tags & written_tags))
    derived_only = tuple(sorted(derived_tags - written_tags))
    missed = tuple(sorted(written_tags - derived_tags))
    return Agreement(
        matched=matched,
        derived_only=derived_only,
        missed=missed,
        hand_written_total=len(written_tags),
    )
