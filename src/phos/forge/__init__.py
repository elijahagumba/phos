"""FORGE — the orchestration layer over GENESIS.

FORGE moves a unit of work through eleven named states, gives each mandate role its own worktree,
and refuses to pass three human approval gates. It does not hold a research record: a declaration,
a measurement and a verdict live in ``docs/genesis/`` and are reached through
:mod:`phos.forge.genesis_api`, which delegates rather than duplicates.

The specification is ``docs/forge/SPEC.md`` and the protocol is
``docs/forge/protocol/forge-protocol-v1.md``. Neither lifts a rule in
``docs/rules/phos-execution-master.md`` or ``docs/rules/data-tiers.md``.
"""

from __future__ import annotations

from phos.forge.protocol import PROTOCOL_VERSION

__all__ = ["PROTOCOL_VERSION"]
