"""Name tokens that suggest a role or a kind. A token is not a declaration (ADR 0220)."""

from __future__ import annotations

import re
from typing import Final, NamedTuple

from phos.atlas.onboarding._models import SuggestionEvidence, TagKind
from phos.atlas.signal_roles import SignalRole

_EQUIPMENT: Final = frozenset({TagKind.VALVE, TagKind.PUMP})
_SETPOINT_WORDS: Final = frozenset({"setpoint", "set-point", "demand", "sp"})
_ACTUATOR_WORDS: Final = frozenset({"command", "commands", "position"})
_KIND_WORDS: Final[dict[str, TagKind]] = {
    "flow": TagKind.FLOW,
    "flowrate": TagKind.FLOW,
    "inflow": TagKind.FLOW,
    "outflow": TagKind.FLOW,
    "pressure": TagKind.PRESSURE,
    "level": TagKind.LEVEL,
    "pump": TagKind.PUMP,
    "pumps": TagKind.PUMP,
    "valve": TagKind.VALVE,
    "valves": TagKind.VALVE,
}


class _CodeSpec(NamedTuple):
    code: str
    kind: TagKind | None
    role: SignalRole
    meaning: str


# Longer codes are matched first, so FIT is not read as FI and LCP is not read as LT.
_CODES: Final[tuple[_CodeSpec, ...]] = (
    _CodeSpec("FCV", TagKind.VALVE, SignalRole.ACTUATOR, "flow control valve"),
    _CodeSpec("PCV", TagKind.VALVE, SignalRole.ACTUATOR, "pressure control valve"),
    _CodeSpec("LCV", TagKind.VALVE, SignalRole.ACTUATOR, "level control valve"),
    _CodeSpec("TCV", TagKind.VALVE, SignalRole.ACTUATOR, "temperature control valve"),
    _CodeSpec("LCP", TagKind.PUMP, SignalRole.ACTUATOR, "pump"),
    _CodeSpec("PMP", TagKind.PUMP, SignalRole.ACTUATOR, "pump"),
    _CodeSpec("FIT", TagKind.FLOW, SignalRole.SENSOR, "flow indicating transmitter"),
    _CodeSpec("PIT", TagKind.PRESSURE, SignalRole.SENSOR, "pressure indicating transmitter"),
    _CodeSpec("LIT", TagKind.LEVEL, SignalRole.SENSOR, "level indicating transmitter"),
    _CodeSpec("TIT", None, SignalRole.SENSOR, "temperature indicating transmitter"),
    _CodeSpec("SIT", None, SignalRole.SENSOR, "speed indicating transmitter"),
    _CodeSpec("FT", TagKind.FLOW, SignalRole.SENSOR, "flow transmitter"),
    _CodeSpec("PT", TagKind.PRESSURE, SignalRole.SENSOR, "pressure transmitter"),
    _CodeSpec("LT", TagKind.LEVEL, SignalRole.SENSOR, "level transmitter"),
    _CodeSpec("TT", None, SignalRole.SENSOR, "temperature transmitter"),
    _CodeSpec("FI", TagKind.FLOW, SignalRole.SENSOR, "flow indicator"),
    _CodeSpec("PI", TagKind.PRESSURE, SignalRole.SENSOR, "pressure indicator"),
    _CodeSpec("LI", TagKind.LEVEL, SignalRole.SENSOR, "level indicator"),
    _CodeSpec("FE", TagKind.FLOW, SignalRole.SENSOR, "flow element"),
    _CodeSpec("PE", TagKind.PRESSURE, SignalRole.SENSOR, "pressure element"),
    _CodeSpec("LE", TagKind.LEVEL, SignalRole.SENSOR, "level element"),
    _CodeSpec("FV", TagKind.VALVE, SignalRole.ACTUATOR, "flow valve"),
    _CodeSpec("PV", TagKind.VALVE, SignalRole.ACTUATOR, "pressure valve"),
    _CodeSpec("LV", TagKind.VALVE, SignalRole.ACTUATOR, "level valve"),
)
_BY_CODE: Final[dict[str, _CodeSpec]] = {spec.code: spec for spec in _CODES}
_CODE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:(?<=^)|(?<=[^A-Za-z]))(?P<code>"
    + "|".join(sorted((spec.code for spec in _CODES), key=len, reverse=True))
    + r")(?P<num>\d+)?(?P<suffix>[DZ])?(?![A-Za-z])",
    re.IGNORECASE,
)
# ``\b`` treats ``_`` as a word character, so ``clearwell_level_setpoint_m`` would be one word.
_WORD_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(set-point|setpoint|demand|commands|command|position|flowrate|inflow|outflow|flow|"
    r"pressure|level|pumps|pump|valves|valve|sp)"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)


class _CodeHit(NamedTuple):
    spec: _CodeSpec
    suffix: str
    start: int


def from_name(
    tag: str,
) -> tuple[TagKind | None, SignalRole | None, tuple[SuggestionEvidence, ...]]:
    """Read a role and a kind from a tag's name, and name the tokens.

    Args:
        tag: The historian or capture name.

    Returns:
        The kind, the role, and the token evidence. The role is ``None`` when no token named
        one. The kind is ``None`` when no token named one of the five kinds.
    """
    code = _best_code(tag)
    words = tuple(match.group(0).lower() for match in _WORD_RE.finditer(tag))
    kind = code.spec.kind if code is not None else None
    kind_word: str | None = None
    if kind is None:
        for word in words:
            mapped = _KIND_WORDS.get(word)
            if mapped is not None:
                kind = mapped
                kind_word = word
                break
    setpoint_word = next((word for word in words if word in _SETPOINT_WORDS), None)
    actuator_word = next((word for word in words if word in _ACTUATOR_WORDS), None)
    role = _role(code, kind, setpoint_word, actuator_word)
    evidence = _evidence(code, kind, kind_word, role, setpoint_word, actuator_word)
    return kind, role, evidence


def _role(
    code: _CodeHit | None,
    kind: TagKind | None,
    setpoint_word: str | None,
    actuator_word: str | None,
) -> SignalRole | None:
    if setpoint_word is not None:
        return SignalRole.SETPOINT
    if actuator_word is not None:
        return SignalRole.ACTUATOR
    if code is not None:
        return code.spec.role
    if kind in (TagKind.PUMP, TagKind.VALVE):
        return SignalRole.ACTUATOR
    if kind in (TagKind.FLOW, TagKind.PRESSURE, TagKind.LEVEL):
        return SignalRole.SENSOR
    return None


def _evidence(
    code: _CodeHit | None,
    kind: TagKind | None,
    kind_word: str | None,
    role: SignalRole | None,
    setpoint_word: str | None,
    actuator_word: str | None,
) -> tuple[SuggestionEvidence, ...]:
    items: list[SuggestionEvidence] = []
    if code is not None:
        items.append(_code_evidence(code))
        items.extend(_suffix_evidence(code))
    elif kind_word is not None and kind is not None:
        items.append(_word_kind_evidence(kind_word, kind, role, actuator_word))
    if setpoint_word is not None:
        items.append(
            SuggestionEvidence(token=setpoint_word, text=f"token {setpoint_word} (setpoint)")
        )
    elif actuator_word is not None:
        items.append(
            SuggestionEvidence(token=actuator_word, text=f"token {actuator_word} (actuator)")
        )
    if not items:
        items.append(
            SuggestionEvidence(
                token="none",
                text="no token in the tag name matched a role or a kind",
            )
        )
    return tuple(items)


def _code_evidence(code: _CodeHit) -> SuggestionEvidence:
    if code.spec.kind is None:
        text = (
            f"token {code.spec.code} ({code.spec.meaning}); "
            "not one of flow, pressure, level, pump, valve"
        )
    else:
        text = f"token {code.spec.code} ({code.spec.meaning})"
    return SuggestionEvidence(token=code.spec.code, text=text)


def _word_kind_evidence(
    kind_word: str,
    kind: TagKind,
    role: SignalRole | None,
    actuator_word: str | None,
) -> SuggestionEvidence:
    if role is SignalRole.SENSOR:
        how = "no setpoint or command token, so the role suggested is sensor"
    elif role is SignalRole.ACTUATOR and actuator_word is None:
        how = "no setpoint token, so the role suggested is actuator"
    else:
        how = f"kind {kind.value}"
    return SuggestionEvidence(token=kind_word, text=f"token {kind_word}; {how}")


def _suffix_evidence(code: _CodeHit) -> tuple[SuggestionEvidence, ...]:
    if not code.suffix:
        return ()
    token = f"{code.spec.code}{code.suffix}"
    if code.suffix == "D" and code.spec.kind in _EQUIPMENT:
        return (SuggestionEvidence(token=token, text="suffix D (command)"),)
    if code.suffix == "Z" and code.spec.kind in _EQUIPMENT:
        return (SuggestionEvidence(token=token, text="suffix Z (reported position)"),)
    if code.suffix == "Z" and code.spec.role is SignalRole.SENSOR:
        text = f"suffix Z on transmitter token {code.spec.code}; role stays sensor"
        return (SuggestionEvidence(token=token, text=text),)
    return ()


def _best_code(tag: str) -> _CodeHit | None:
    hits = [
        _CodeHit(
            _BY_CODE[match.group("code").upper()],
            (match.group("suffix") or "").upper(),
            match.start(),
        )
        for match in _CODE_RE.finditer(tag)
    ]
    if not hits:
        return None
    hits.sort(key=lambda hit: (-len(hit.spec.code), hit.start))
    return hits[0]
