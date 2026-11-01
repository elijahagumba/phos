"""Read the pinned controller source as text, with its digests checked.

ADR 0370 names three files of the ICSSim checkout at commit
``bcfd1844d3f063850c69f2643f6a052bac03d8ec`` and the sha256 of each. This module
reads those bytes and nothing else. It does not import them, does not execute
them, and does not start a simulator: the files arrive here as `str`, and the
only thing done with that string is `ast.parse` in `phos.atlas.code_law.derive`,
which builds a tree and runs no statement.

It does not read ``data/phos-icssim-dev/roles.toml``. That file is a hand-written
quotation of the same source, and using it would make the check circular — the
derivation would be compared against a transcription of itself.

A digest that does not match is a **refusal of the run**, not a warning: the
reader returns the refusals and no source. An absent file and a file that is not
UTF-8 are refusals too. Nothing here raises on bad input.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

__all__ = [
    "DECLARED_SOURCES",
    "DeclaredSource",
    "PinnedSource",
    "RefusalReason",
    "SourceRead",
    "SourceRefusal",
    "SourceText",
    "pinned_source_from_text",
    "read_pinned_source",
]

#: The pinned commit the digests below belong to. Recorded, never fetched here.
ICSSIM_COMMIT: Final = "bcfd1844d3f063850c69f2643f6a052bac03d8ec"

PLC1_RELATIVE: Final = "src/PLC1.py"
CONFIGS_RELATIVE: Final = "src/Configs.py"
DEVICE_RELATIVE: Final = "src/ics_sim/Device.py"


@dataclass(frozen=True)
class DeclaredSource:
    """One file ADR 0370 allows the derivation to read.

    Attributes:
        relative: The path inside the pinned checkout.
        sha256: The digest ADR 0370 records for that file.
    """

    relative: str
    sha256: str


#: The three files, in the order ADR 0370's table lists them. Adding a fourth is
#: a new declaration, not an edit here.
DECLARED_SOURCES: Final[tuple[DeclaredSource, ...]] = (
    DeclaredSource(
        relative=PLC1_RELATIVE,
        sha256="4651130bba9f137108c0426a6fdeb829db8705ea7eeedd40dfab378c9cf51316",
    ),
    DeclaredSource(
        relative=CONFIGS_RELATIVE,
        sha256="242e19fe346550fc4614f3511d6eacd91c0dfadb3e9591fd616570352ad23bd3",
    ),
    DeclaredSource(
        relative=DEVICE_RELATIVE,
        sha256="574660255d62e29e27015baaa797005071a11f14317af9525b6525258464ae92",
    ),
)


class RefusalReason(StrEnum):
    """Why one declared file could not be used. A word, not a rank."""

    FILE_ABSENT = "file absent"
    DIGEST_MISMATCH = "digest mismatch"
    NOT_UTF8 = "not utf-8"


@dataclass(frozen=True)
class SourceRefusal:
    """One declared file this run will not read.

    Attributes:
        relative: The path inside the pinned checkout.
        reason: Which refusal it is.
        expected: The digest ADR 0370 records, or the empty string when the
            refusal is not about a digest.
        found: The digest on disk, or the empty string when there was nothing
            to digest.
    """

    relative: str
    reason: RefusalReason
    expected: str = ""
    found: str = ""


@dataclass(frozen=True)
class SourceText:
    """One declared file, read and digested.

    Attributes:
        relative: The path inside the pinned checkout.
        sha256: The digest of the bytes that were read.
        text: Those bytes, decoded as UTF-8. Never executed.
    """

    relative: str
    sha256: str
    text: str


@dataclass(frozen=True)
class PinnedSource:
    """The three declared files of one pinned checkout.

    Attributes:
        plc1: The control program.
        configs: The tag table, which holds each tag's default.
        device: The guard that says what a mode tag does.
    """

    plc1: SourceText
    configs: SourceText
    device: SourceText


@dataclass(frozen=True)
class SourceRead:
    """The result of one attempt to read the declared files.

    Exactly one side is populated: a read with any refusal returns no source,
    because a partial read is not the declared input.

    Attributes:
        source: The three files, or None when anything was refused.
        refusals: One entry per file that could not be used.
    """

    source: PinnedSource | None
    refusals: tuple[SourceRefusal, ...]


def _digest(data: bytes) -> str:
    """Return the sha256 of ``data`` as lowercase hex."""
    return hashlib.sha256(data).hexdigest()


def read_pinned_source(root: Path, *, digests: Mapping[str, str] | None = None) -> SourceRead:
    """Read the three declared files under ``root``, checking each digest.

    Args:
        root: The pinned checkout, the directory that holds ``src/``.
        digests: Expected digests by relative path, for a caller that is
            standing other bytes in for the pinned ones — a test, or a later
            declaration that pins a different commit. Omitted means
            `DECLARED_SOURCES`, which is what the declared command uses.

    Returns:
        The three files when every digest matched, otherwise no source and one
        refusal per file that could not be used.
    """
    declared_digests = {source.relative: source.sha256 for source in DECLARED_SOURCES}
    expected = dict(digests) if digests is not None else declared_digests
    refusals: list[SourceRefusal] = []
    read: dict[str, SourceText] = {}
    for declared in DECLARED_SOURCES:
        relative = declared.relative
        want = expected.get(relative, declared.sha256)
        path = root / relative
        if not path.is_file():
            refusals.append(
                SourceRefusal(relative=relative, reason=RefusalReason.FILE_ABSENT, expected=want)
            )
            continue
        data = path.read_bytes()
        found = _digest(data)
        if found != want:
            refusals.append(
                SourceRefusal(
                    relative=relative,
                    reason=RefusalReason.DIGEST_MISMATCH,
                    expected=want,
                    found=found,
                )
            )
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            refusals.append(
                SourceRefusal(
                    relative=relative,
                    reason=RefusalReason.NOT_UTF8,
                    expected=want,
                    found=found,
                )
            )
            continue
        read[relative] = SourceText(relative=relative, sha256=found, text=text)
    if refusals:
        return SourceRead(source=None, refusals=tuple(refusals))
    return SourceRead(
        source=PinnedSource(
            plc1=read[PLC1_RELATIVE],
            configs=read[CONFIGS_RELATIVE],
            device=read[DEVICE_RELATIVE],
        ),
        refusals=(),
    )


def pinned_source_from_text(*, plc1: str, configs: str, device: str) -> PinnedSource:
    """Build a `PinnedSource` from text already in hand, digesting each part.

    The declared command reads files. This exists for a caller that holds the
    text instead, so the derivation can be exercised without the pinned
    checkout and without spending the declared score.

    Args:
        plc1: The control program's text.
        configs: The tag table's text.
        device: The guard's text.

    Returns:
        The three parts, each carrying the digest of the text supplied.
    """
    return PinnedSource(
        plc1=SourceText(relative=PLC1_RELATIVE, sha256=_digest(plc1.encode("utf-8")), text=plc1),
        configs=SourceText(
            relative=CONFIGS_RELATIVE, sha256=_digest(configs.encode("utf-8")), text=configs
        ),
        device=SourceText(
            relative=DEVICE_RELATIVE, sha256=_digest(device.encode("utf-8")), text=device
        ),
    )
