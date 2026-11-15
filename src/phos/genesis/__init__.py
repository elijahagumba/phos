"""GENESIS — the PHOS research record as data, and the gates that read it.

The charter is ``docs/rules/genesis-charter.md``, loaded by both Cursor and Claude Code. This
package is the half a charter cannot be: the record kinds (``records``), what each rung of the
discovery ladder demands (``levels``), and the store that holds them (``store``). The command-line
surface both tools drive is ``scripts/genesis.py``.

Nothing here lifts a prohibition. ``docs/rules/phos-execution-master.md`` and
``docs/rules/data-tiers.md`` win over this package, and a tier ``never`` corpus is refused at
declaration time rather than argued about later.
"""

from phos.genesis.records import (
    Bar,
    Declaration,
    Experiment,
    Finding,
    Measurement,
    Priority,
    Question,
    Review,
    Verdict,
)

__all__ = [
    "Bar",
    "Declaration",
    "Experiment",
    "Finding",
    "Measurement",
    "Priority",
    "Question",
    "Review",
    "Verdict",
]
