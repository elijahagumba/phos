"""The small readings of the controller source's syntax tree.

Each function here answers one question about the tree and nothing else: which
modes the guard names, what the tag table says a tag defaults to, which blocks
of ``_logic`` are guarded, what a ``self._set`` call writes. They return None or
an empty result when the tree does not hold what was asked for, so the caller
can turn that into a refusal with a name on it.

Nothing here runs the source. `ast.parse` builds a tree; no statement in that
tree is executed, no module is imported, and no expression is evaluated.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from typing import Final

from phos.atlas.code_law.law import DerivedForcedWrite, DerivedGuard
from phos.atlas.code_law.source import CONFIGS_RELATIVE, DEVICE_RELATIVE, PLC1_RELATIVE

__all__ = [
    "DEFAULT_KEY",
    "GUARD",
    "LOGIC",
    "OPERATORS",
    "SET",
    "TAG_CLASS",
    "TAG_LIST",
    "forced_writes_from_device",
    "get_tag",
    "guard_from_device",
    "guard_tags",
    "local_tags",
    "logic_blocks",
    "number",
    "number_text",
    "set_value",
    "tag_constant",
    "tag_default_node",
    "tag_table",
]

LOGIC: Final = "_logic"
GUARD: Final = "_check_manual_input"
TAG_CLASS: Final = "TAG"
TAG_LIST: Final = "TAG_LIST"
DEFAULT_KEY: Final = "default"
SET: Final = "_set"
GET: Final = "_get"

OPERATORS: Final[Mapping[type[ast.cmpop], str]] = {
    ast.Gt: ">",
    ast.Lt: "<",
    ast.GtE: ">=",
    ast.LtE: "<=",
    ast.Eq: "==",
    ast.NotEq: "!=",
}


def number(node: ast.expr) -> float | None:
    """Return a numeric constant's value, or None when the node is not one."""
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return float(node.value)
    return None


def number_text(node: ast.expr) -> str:
    """Return a numeric constant as the source writes it."""
    return ast.unparse(node)


def tag_constant(node: ast.expr) -> str | None:
    """Return the ``TAG.TAG_X`` constant name a node refers to, or None.

    The control program writes ``TAG.TAG_TANK_LEVEL_VALUE``; the tag table
    writes the bare ``TAG_TANK_LEVEL_VALUE`` as a dictionary key. Both are
    accepted, and nothing else is.
    """
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if node.value.id == TAG_CLASS:
            return node.attr
        return None
    if isinstance(node, ast.Name):
        return node.id
    return None


def tag_table(configs: str) -> tuple[Mapping[str, str], Mapping[str, float], tuple[str, ...]]:
    """Return tag constants, their defaults, and refusals, from ``Configs.py``.

    Returns:
        The constant name to tag string map, the tag string to default map, and
        one refusal line per thing that was not found.
    """
    names: dict[str, str] = {}
    defaults: dict[str, float] = {}
    refusals: list[str] = []
    tree = ast.parse(configs)
    tag_class: ast.ClassDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == TAG_CLASS:
            tag_class = node
            break
    if tag_class is None:
        return names, defaults, (f"{CONFIGS_RELATIVE}: no class {TAG_CLASS}",)
    table: ast.Dict | None = None
    for statement in tag_class.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str):
            names[target.id] = statement.value.value
        elif target.id == TAG_LIST and isinstance(statement.value, ast.Dict):
            table = statement.value
    if table is None:
        refusals.append(f"{CONFIGS_RELATIVE}: no {TAG_LIST} in class {TAG_CLASS}")
        return names, defaults, tuple(refusals)
    for key, value in zip(table.keys, table.values, strict=True):
        if key is None:
            continue
        constant = tag_constant(key)
        if constant is None or constant not in names or not isinstance(value, ast.Dict):
            continue
        for entry_key, entry_value in zip(value.keys, value.values, strict=True):
            if (
                isinstance(entry_key, ast.Constant)
                and entry_key.value == DEFAULT_KEY
                and (found := number(entry_value)) is not None
            ):
                defaults[names[constant]] = found
    return names, defaults, tuple(refusals)


def _guard_definition(device: str) -> tuple[ast.FunctionDef | None, tuple[str, ...]]:
    """Return the ``_check_manual_input`` definition, or a refusal."""
    tree = ast.parse(device)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == GUARD:
            return node, ()
    return None, (f"{DEVICE_RELATIVE}: no function {GUARD}",)


def _manual_branches(definition: ast.FunctionDef) -> list[tuple[float, ast.If]]:
    """Return each ``if mode == N`` branch that returns True, with its mode."""
    found: list[tuple[float, ast.If]] = []
    for node in ast.walk(definition):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        if not _returns_true(node.body):
            continue
        compare = node.test
        if len(compare.ops) != 1 or not isinstance(compare.ops[0], ast.Eq):
            continue
        mode = number(compare.comparators[0])
        if mode is not None:
            found.append((mode, node))
    return found


def guard_from_device(device: str) -> tuple[DerivedGuard | None, tuple[str, ...]]:
    """Return the exclusion guard ``_check_manual_input`` names, and refusals."""
    definition, refusals = _guard_definition(device)
    if definition is None:
        return None, refusals
    modes = [mode for mode, _branch in _manual_branches(definition)]
    if not modes:
        return None, (f"{DEVICE_RELATIVE}: {GUARD} names no manual mode",)
    return (
        DerivedGuard.exclusion(tuple(modes), file=DEVICE_RELATIVE, line=definition.lineno),
        (),
    )


def forced_writes_from_device(
    device: str,
) -> tuple[tuple[DerivedForcedWrite, ...] | None, tuple[str, ...]]:
    """Return the actuator writes ``_check_manual_input`` forces at modes 1 and 2.

    Each write is the ``self._set(actuator_tag, value)`` call inside a branch that
    returns True. The value's source text is taken from that call's node, not
    rebuilt from the float. ADR 0382 bar 4 requires these writes as a stated
    fact on the derived law, not folded into the comparison rule.
    """
    definition, refusals = _guard_definition(device)
    if definition is None:
        return None, refusals
    writes: list[DerivedForcedWrite] = []
    for mode, branch in _manual_branches(definition):
        written: DerivedForcedWrite | None = None
        for statement in branch.body:
            found = set_value(statement)
            if found is None:
                continue
            _constant, value_node = found
            value = number(value_node)
            if value is None:
                continue
            written = DerivedForcedWrite(
                mode=mode,
                value=value,
                literal_text=number_text(value_node),
                file=DEVICE_RELATIVE,
                line=value_node.lineno,
            )
            break
        if written is None:
            return None, (f"{DEVICE_RELATIVE}: {GUARD} at mode {mode} writes no actuator value",)
        writes.append(written)
    if not writes:
        return None, (f"{DEVICE_RELATIVE}: {GUARD} forces no actuator write",)
    return tuple(writes), ()


def tag_default_node(configs: str, tag: str) -> ast.expr | None:
    """Return the AST node of ``tag``'s ``'default'`` value in ``TAG_LIST``.

    The node is what the source writes, so ``literal_text`` can quote it. A
    missing tag or a missing default returns None.
    """
    tree = ast.parse(configs)
    names: dict[str, str] = {}
    table: ast.Dict | None = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != TAG_CLASS:
            continue
        for statement in node.body:
            if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
                continue
            target = statement.targets[0]
            if not isinstance(target, ast.Name):
                continue
            if isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str):
                names[target.id] = statement.value.value
            elif target.id == TAG_LIST and isinstance(statement.value, ast.Dict):
                table = statement.value
    if table is None:
        return None
    for key, value in zip(table.keys, table.values, strict=True):
        if key is None or not isinstance(value, ast.Dict):
            continue
        constant = tag_constant(key)
        if constant is None or names.get(constant) != tag:
            continue
        for entry_key, entry_value in zip(value.keys, value.values, strict=True):
            if isinstance(entry_key, ast.Constant) and entry_key.value == DEFAULT_KEY:
                return entry_value
    return None


def _returns_true(body: Sequence[ast.stmt]) -> bool:
    """Return whether ``body`` returns the constant True at its own level."""
    return any(
        isinstance(statement, ast.Return)
        and isinstance(statement.value, ast.Constant)
        and statement.value.value is True
        for statement in body
    )


def logic_blocks(plc1: str) -> tuple[tuple[ast.If, ...], tuple[str, ...]]:
    """Return the guarded blocks of ``PLC1._logic``, in source order."""
    tree = ast.parse(plc1)
    logic: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == LOGIC:
            logic = node
            break
    if logic is None:
        return (), (f"{PLC1_RELATIVE}: no function {LOGIC}",)
    blocks = [
        statement
        for statement in logic.body
        if isinstance(statement, ast.If) and _is_guarded(statement.test)
    ]
    if not blocks:
        return (), (f"{PLC1_RELATIVE}: {LOGIC} holds no {GUARD} block",)
    return tuple(blocks), ()


def _is_guarded(test: ast.expr) -> bool:
    """Return whether ``test`` is ``not self._check_manual_input(...)``."""
    if not isinstance(test, ast.UnaryOp) or not isinstance(test.op, ast.Not):
        return False
    call = test.operand
    return (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == GUARD
    )


def guard_tags(test: ast.expr) -> tuple[str | None, str | None]:
    """Return the mode and status tag constants the guard call was given."""
    if not isinstance(test, ast.UnaryOp):
        return None, None
    call = test.operand
    if not isinstance(call, ast.Call) or len(call.args) < 2:
        return None, None
    return tag_constant(call.args[0]), tag_constant(call.args[1])


def local_tags(body: Sequence[ast.stmt]) -> Mapping[str, str]:
    """Return local names bound to ``self._get(TAG.X)``, as tag constants."""
    bound: dict[str, str] = {}
    for statement in body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if not isinstance(target, ast.Name):
            continue
        constant = get_tag(statement.value)
        if constant is not None:
            bound[target.id] = constant
    return bound


def get_tag(node: ast.expr) -> str | None:
    """Return the tag constant of a ``self._get(TAG.X)`` call, or None."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == GET
        and len(node.args) == 1
    ):
        return tag_constant(node.args[0])
    return None


def set_value(statement: ast.stmt) -> tuple[str, ast.expr] | None:
    """Return the tag constant and value node of a ``self._set`` call."""
    if not isinstance(statement, ast.Expr):
        return None
    call = statement.value
    if (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == SET
        and len(call.args) == 2
    ):
        constant = tag_constant(call.args[0])
        if constant is not None:
            return constant, call.args[1]
    return None
