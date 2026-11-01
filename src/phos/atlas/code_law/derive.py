"""Derive the valve law from the pinned controller source.

The source arrives as text from `phos.atlas.code_law.source` and is turned into
an abstract syntax tree with `ast.parse`. A tree is a description of statements,
not a run of them: nothing here imports the controller program, calls a function
it defines, or evaluates one of its expressions. Formatting cannot reach a tree,
so a file wrapped differently derives the same law.

**Where each literal comes from (ADR 0370's provenance table, in code).**

- Close and open are the second argument of the two ``self._set`` calls in
  ``PLC1._logic``.
- The belt literal is the right-hand side of the belt comparison in the same
  function.
- The release literal is the ``'default'`` of the two valve mode tags in
  ``Configs.TAG.TAG_LIST``. **It is not in the control program**, so a
  derivation that read only ``PLC1.py`` could not produce it.
- The guard is ``_check_manual_input`` in ``ics_sim/Device.py``, which names the
  modes that are manual. It does not name a release mode.

The release literal and the guard are two different facts, and
`phos.atlas.code_law.law` keeps them apart rather than folding one into the
other. The release literal is **not** hard-coded here to make the guard match
the hand-written law, and ``controller_valve`` is not edited.

Anything the provenance table names and the source does not hold is a refusal,
returned rather than raised. A refusal is a result.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from phos.atlas.code_law.law import (
    DerivedBranch,
    DerivedCondition,
    DerivedLiteral,
    DerivedRule,
    DerivedValveLaw,
    Side,
)
from phos.atlas.code_law.parse import (
    GUARD,
    LOGIC,
    OPERATORS,
    forced_writes_from_device,
    get_tag,
    guard_from_device,
    guard_tags,
    local_tags,
    logic_blocks,
    number,
    number_text,
    set_value,
    tag_default_node,
    tag_table,
)
from phos.atlas.code_law.source import CONFIGS_RELATIVE, ICSSIM_COMMIT, PLC1_RELATIVE, PinnedSource

__all__ = ["Derivation", "derive_valve_law"]


_INPUT_MODE_TAG: Final = "tank_input_valve_mode"
_OUTPUT_MODE_TAG: Final = "tank_output_valve_mode"
_BELT_TAG: Final = "bottle_distance_to_filler_value"


@dataclass(frozen=True)
class Derivation:
    """One attempt to derive the law.

    Attributes:
        law: The derived law, or None when the source did not hold what ADR
            0370's provenance table names.
        refusals: What was missing, one line each. A refusal is a result.
    """

    law: DerivedValveLaw | None
    refusals: tuple[str, ...]


def _branch_conditions(
    test: ast.expr, tags: Mapping[str, str], names: Mapping[str, str]
) -> tuple[DerivedCondition, ...]:
    """Return the comparisons of one branch test, in source order.

    An ``or`` of comparisons becomes several conditions; a bare comparison
    becomes one. Anything else returns nothing, which refuses the branch rather
    than reading a shape the provenance table does not name.
    """
    parts: list[ast.expr] = []
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or):
        parts.extend(test.values)
    else:
        parts.append(test)
    found: list[DerivedCondition] = []
    for part in parts:
        if not isinstance(part, ast.Compare) or len(part.ops) != 1:
            continue
        operator = OPERATORS.get(type(part.ops[0]))
        if operator is None:
            operator = type(part.ops[0]).__name__
        left = _signal(part.left, tags, names)
        if left is None:
            continue
        right_node = part.comparators[0]
        right_signal = _signal(right_node, tags, names)
        right_literal = None if right_signal is not None else number(right_node)
        if right_signal is None and right_literal is None:
            continue
        right_literal_text = None if right_signal is not None else number_text(right_node)
        found.append(
            DerivedCondition(
                left=left,
                operator=operator,
                right_signal=right_signal,
                right_literal=right_literal,
                right_literal_text=right_literal_text,
                line=part.lineno,
            )
        )
    return tuple(found)


def _signal(node: ast.expr, tags: Mapping[str, str], names: Mapping[str, str]) -> str | None:
    """Return the tag name a node reads, through a local or a ``_get`` call."""
    if isinstance(node, ast.Name) and node.id in tags:
        return names.get(tags[node.id])
    constant = get_tag(node)
    if constant is not None:
        return names.get(constant)
    return None


def _rule(
    block: ast.If, names: Mapping[str, str]
) -> tuple[DerivedRule | None, tuple[DerivedLiteral, ...], tuple[str, ...]]:
    """Return one side's rule, the literals it yielded, and any refusals."""
    mode_constant, status_constant = guard_tags(block.test)
    if mode_constant is None or status_constant is None:
        return None, (), (f"{PLC1_RELATIVE}: a {GUARD} block names no mode and status tag",)
    mode_signal = names.get(mode_constant)
    status_signal = names.get(status_constant)
    if mode_signal is None or status_signal is None:
        return None, (), (f"{PLC1_RELATIVE}: {mode_constant} or {status_constant} has no tag name",)
    side = Side.INPUT if mode_signal == _INPUT_MODE_TAG else Side.OUTPUT
    locals_bound = local_tags(block.body)
    inner = [statement for statement in block.body if isinstance(statement, ast.If)]
    if not inner:
        return None, (), (f"{PLC1_RELATIVE}: the {side.value} block holds no comparison",)
    branches, otherwise, literals = _branches(inner[0], locals_bound, names, status_constant)
    if not branches:
        return None, (), (f"{PLC1_RELATIVE}: the {side.value} comparison yielded no branch",)
    return (
        DerivedRule(
            side=side,
            branches=branches,
            otherwise=otherwise,
            mode_signal=mode_signal,
            status_signal=status_signal,
        ),
        literals,
        (),
    )


def _branches(
    node: ast.If,
    locals_bound: Mapping[str, str],
    names: Mapping[str, str],
    status_constant: str,
) -> tuple[tuple[DerivedBranch, ...], float | None, tuple[DerivedLiteral, ...]]:
    """Walk an ``if`` / ``elif`` / ``else`` chain into ordered branches.

    The chain's order is the source's order, which is what the input side's
    ``elif`` makes load-bearing. An ``else`` becomes the rule's otherwise
    value; no ``else`` leaves it None, which is silence rather than a default.
    """
    branches: list[DerivedBranch] = []
    literals: list[DerivedLiteral] = []
    otherwise: float | None = None
    current: ast.If | None = node
    while current is not None:
        conditions = _branch_conditions(current.test, locals_bound, names)
        written = _written(current.body, status_constant)
        if conditions and written is not None:
            value, value_node = written
            branches.append(
                DerivedBranch(conditions=conditions, writes=value, line=current.test.lineno)
            )
            literals.append(
                DerivedLiteral(
                    name="close" if value == 0.0 else "open",
                    value=value,
                    literal_text=number_text(value_node),
                    file=PLC1_RELATIVE,
                    line=value_node.lineno,
                )
            )
        tail = current.orelse
        if len(tail) == 1 and isinstance(tail[0], ast.If):
            current = tail[0]
            continue
        if tail:
            written = _written(tail, status_constant)
            if written is not None:
                otherwise, value_node = written
                literals.append(
                    DerivedLiteral(
                        name="close" if otherwise == 0.0 else "open",
                        value=otherwise,
                        literal_text=number_text(value_node),
                        file=PLC1_RELATIVE,
                        line=value_node.lineno,
                    )
                )
        current = None
    return tuple(branches), otherwise, tuple(literals)


def _written(body: Sequence[ast.stmt], status_constant: str) -> tuple[float, ast.expr] | None:
    """Return the value a body writes to ``status_constant``, and its node."""
    for statement in body:
        found = set_value(statement)
        if found is None:
            continue
        constant, value_node = found
        if constant != status_constant:
            continue
        found_number = number(value_node)
        if found_number is not None:
            return found_number, value_node
    return None


def _belt_literal(rules: Sequence[DerivedRule]) -> DerivedLiteral | None:
    """Return the belt comparison's literal, quoting the source node's text."""
    for rule in rules:
        for branch in rule.branches:
            for condition in branch.conditions:
                if (
                    condition.left == _BELT_TAG
                    and condition.right_literal is not None
                    and condition.right_literal_text is not None
                ):
                    return DerivedLiteral(
                        name="belt_past_filler",
                        value=condition.right_literal,
                        literal_text=condition.right_literal_text,
                        file=PLC1_RELATIVE,
                        line=condition.line,
                    )
    return None


def _release_literal(
    configs: str, defaults: Mapping[str, float]
) -> tuple[DerivedLiteral | None, tuple[str, ...]]:
    """Return the release literal, quoting the source node's text.

    The two tags must agree. If they do not, there is no single release literal
    to derive, and that is a refusal rather than a choice between them. The
    stored source text is the text of the ``'default'`` node at the cited file
    and line, not a string rebuilt from the float (ADR 0382 bar 1).
    """
    wanted = (_INPUT_MODE_TAG, _OUTPUT_MODE_TAG)
    missing = [tag for tag in wanted if tag not in defaults]
    if missing:
        return None, (f"{CONFIGS_RELATIVE}: no default for {', '.join(missing)}",)
    values = {defaults[tag] for tag in wanted}
    if len(values) != 1:
        return None, (f"{CONFIGS_RELATIVE}: the two valve mode defaults disagree",)
    value = values.pop()
    node = tag_default_node(configs, _INPUT_MODE_TAG)
    if node is None:
        return None, (f"{CONFIGS_RELATIVE}: no default node for {_INPUT_MODE_TAG}",)
    return (
        DerivedLiteral(
            name="release_mode",
            value=value,
            literal_text=number_text(node),
            file=CONFIGS_RELATIVE,
            line=node.lineno,
        ),
        (),
    )


def derive_valve_law(source: PinnedSource) -> Derivation:
    """Derive the valve law from the three declared files.

    Args:
        source: The pinned files, already digest-checked by
            `phos.atlas.code_law.source`.

    Returns:
        The derived law, or no law and one refusal line per thing ADR 0370's
        provenance table names that the source did not hold.
    """
    refusals: list[str] = []
    names, defaults, table_refusals = tag_table(source.configs.text)
    refusals.extend(table_refusals)
    guard, guard_refusals = guard_from_device(source.device.text)
    refusals.extend(guard_refusals)
    forced, forced_refusals = forced_writes_from_device(source.device.text)
    refusals.extend(forced_refusals)
    blocks, block_refusals = logic_blocks(source.plc1.text)
    refusals.extend(block_refusals)

    rules: list[DerivedRule] = []
    literals: list[DerivedLiteral] = []
    for block in blocks:
        rule, block_literals, rule_refusals = _rule(block, names)
        refusals.extend(rule_refusals)
        if rule is not None:
            rules.append(rule)
            literals.extend(block_literals)
    if len({rule.side for rule in rules}) != len(Side):
        refusals.append(f"{PLC1_RELATIVE}: {LOGIC} did not yield both valve rules")

    release, release_refusals = _release_literal(source.configs.text, defaults)
    refusals.extend(release_refusals)
    belt = _belt_literal(rules)
    if belt is None:
        refusals.append(f"{PLC1_RELATIVE}: the output comparison names no belt literal")

    if guard is None or forced is None or release is None or belt is None or refusals:
        return Derivation(law=None, refusals=tuple(refusals))

    return Derivation(
        law=DerivedValveLaw(
            literals=(*_named_once(literals), release, belt),
            guard=guard,
            forced_writes=forced,
            rules=tuple(sorted(rules, key=lambda rule: tuple(Side).index(rule.side))),
            commit=ICSSIM_COMMIT,
            digests={
                source.plc1.relative: source.plc1.sha256,
                source.configs.relative: source.configs.sha256,
                source.device.relative: source.device.sha256,
            },
        ),
        refusals=(),
    )


def _named_once(literals: Sequence[DerivedLiteral]) -> tuple[DerivedLiteral, ...]:
    """Return the first literal under each name, in the order first seen.

    The source writes close and open on both sides. One name holds one value,
    and a second write of a different value under the same name would be a
    disagreement inside the source, so the first is kept and the comparison
    bars are what judge whether every branch wrote what was expected.
    """
    seen: dict[str, DerivedLiteral] = {}
    for literal in literals:
        seen.setdefault(literal.name, literal)
    return tuple(seen.values())
