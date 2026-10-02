"""Set a demo result as terminal text: quiet type, one accent, nothing the run did not produce.

The layout follows the README's alert card. A square marks what holds and an open square what does
not; the amber accent is reserved for the one fact that would settle the incident, and appears
nowhere else. Every sentence is either fixed framing or taken from the `DemoResult`, so the
terminal can only say what Atlas and the plant said.

Colour is plain ANSI and is dropped when the caller asks, which ``phos demo`` does when ``NO_COLOR``
is set or the output is not a terminal.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from typing import Final

from phos.demo.pipeline import DemoResult, Stage
from phos.reasoning.analyst import Assessment, NarrativeBrief

__all__ = ["Style", "render_header", "render_result", "render_stage"]

WIDTH: Final = 72
INDENT: Final = "  "
_FILLED: Final = "■"
_OPEN: Final = "□"


@dataclass(frozen=True)
class Style:
    """ANSI styling, or none at all."""

    colour: bool = True

    def _wrap(self, code: str, text: str) -> str:
        return f"\x1b[{code}m{text}\x1b[0m" if self.colour else text

    def bold(self, text: str) -> str:
        """Return ``text`` in bold."""
        return self._wrap("1", text)

    def dim(self, text: str) -> str:
        """Return ``text`` dimmed."""
        return self._wrap("2", text)

    def light(self, text: str) -> str:
        """Return ``text`` in the accent reserved for the settling fact."""
        return self._wrap("1;38;5;214", text)


def _rule(style: Style) -> str:
    return INDENT + style.dim("─" * (WIDTH - len(INDENT)))


def _label(text: str, style: Style) -> str:
    return INDENT + style.dim(text.upper())


def _paragraph(text: str, indent: str = INDENT) -> list[str]:
    return textwrap.wrap(text, width=WIDTH, initial_indent=indent, subsequent_indent=indent)


def _bullet(text: str, mark: str) -> list[str]:
    return textwrap.wrap(
        text,
        width=WIDTH,
        initial_indent=f"{INDENT}{mark} ",
        subsequent_indent=INDENT + "  ",
    )


def render_header(plant_label: str, seed: int, style: Style) -> str:
    """Return the opening lines, printed before the run starts."""
    left = INDENT + style.bold("phos") + style.dim("  demo")
    right = f"{plant_label.lower()} · seed {seed}"
    gap = WIDTH - len(INDENT) - len("phos  demo") - len(right)
    return "\n".join(["", left + " " * max(gap, 2) + style.dim(right), _rule(style), ""])


def render_stage(stage: Stage, style: Style) -> str:
    """Return one progress line for a finished stage."""
    timing = f"{stage.seconds:4.1f} s"
    detail = stage.detail
    room = WIDTH - len(INDENT) - 2 - 13 - len(timing) - 2
    if len(detail) > room:
        detail = detail[: room - 1] + "…"
    return (
        f"{INDENT}{_FILLED} {style.bold(stage.name.ljust(12))} {detail.ljust(room)}  "
        + style.dim(timing)
    )


def _assessment(brief: NarrativeBrief, style: Style) -> list[str]:
    """Lead with the verdict in one bold word, then the brief's own reasoning."""
    line = brief.assessment_line.removeprefix("Assessment:").strip()
    head, _, rest = line.partition(". ")
    head = head.rstrip(".").capitalize() + "."
    lines = [INDENT + style.bold(head)]
    if rest:
        lines += _paragraph(rest[0].upper() + rest[1:])
    return lines


def _explanations(brief: NarrativeBrief, style: Style) -> list[str]:
    lines = [_label("Still on the table", style)]
    width = max(len(e.label.strip()) for e in brief.explanations)
    # Contentful explanations first, most supported first; the residual closes the list.
    ordered = sorted(
        brief.explanations, key=lambda e: (e.is_residual, -len(e.supporting), len(e.contradictory))
    )
    for explanation in ordered:
        label = explanation.label.strip().ljust(width)
        if explanation.is_residual:
            lines.append(
                f"{INDENT}{style.dim(_OPEN)} {style.dim(label)}  {style.dim('always present')}"
            )
            continue
        tally = f"{len(explanation.supporting)} for · {len(explanation.contradictory)} against"
        mark = _FILLED if explanation.supporting else _OPEN
        lines.append(f"{INDENT}{mark} {label}  {style.dim(tally)}")
    return lines


def _settling(brief: NarrativeBrief) -> str:
    """Return the brief's next fact as a sentence, without the template prose after the dash."""
    fact = brief.next_evidence.split(" — ", 1)[0].strip().rstrip(".")
    return fact[0].upper() + fact[1:] + "."


def _closing(result: DemoResult) -> str:
    """Say plainly how Atlas's brief relates to what happened: a tie, a miss or a false alarm."""
    brief = result.brief
    if brief is None:
        if result.unauthorised:
            return "Atlas raised nothing. The unauthorised write went unseen."
        if result.writes:
            return "Atlas raised nothing. The write was authorised, so there was nothing to raise."
        return "Atlas raised nothing, and nothing was written to the plant."
    if result.concerns_truth:
        if brief.assessment is Assessment.UNRESOLVED:
            return (
                "Atlas could not tell which it was. It said so, and named the one fact that "
                "would settle it."
            )
        return "Atlas settled on one explanation. Set it beside what actually happened, above."
    if result.unauthorised:
        return (
            "Atlas missed the unauthorised write: nothing it raised is about it. The incident it "
            "did raise is unrelated to any write, a false alarm."
        )
    if result.writes:
        return (
            "The authorised write raised nothing, which is right. The incident Atlas did raise is "
            "unrelated to it, a false alarm."
        )
    return "Nothing was written to the plant. The incident Atlas raised is a false alarm."


def render_result(result: DemoResult, style: Style) -> str:
    """Return everything printed after the stages: the brief, then the truth, then the caveat."""
    lines: list[str] = ["", _rule(style), ""]
    brief = result.brief
    if brief is None:
        lines += _paragraph("Atlas saw nothing in the live traffic it could not explain.")
    else:
        lines.append(_label(f"Atlas · {result.subject}", style))
        lines.append("")
        lines += _assessment(brief, style)
        lines += ["", _label("What it saw", style)]
        for finding in result.findings:
            lines += _bullet(finding, "·")
        lines += [""]
        lines += _explanations(brief, style)
        lines += ["", INDENT + style.light(f"{_FILLED} WHAT WOULD SETTLE IT")]
        lines += _paragraph(_settling(brief), indent=INDENT + "  ")
        if result.other_incidents:
            lines += ["", INDENT + style.dim(f"+ {result.other_incidents} further incident(s)")]
    lines += ["", _rule(style), "", _label("What actually happened", style)]
    lines += [
        INDENT + style.dim("Read from the simulation after Atlas finished. Atlas never saw it.")
    ]
    lines += [""]
    for truth in result.truth:
        lines += _paragraph(truth)
    lines += [""]
    lines += [INDENT + line.strip() for line in textwrap.wrap(_closing(result), WIDTH - 2)]
    lines += ["", _rule(style)]
    caveat = "A simulated plant and an adversary we wrote. A demonstration, not a measurement."
    lines += [INDENT + style.dim(line.strip()) for line in _paragraph(caveat)]
    return "\n".join([*lines, ""])
