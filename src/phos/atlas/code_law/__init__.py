"""Atlas's code laws: the valve law read out of the controller's own program.

One of Atlas's six declared laws, ``controller_valve``, was copied by hand out
of the ICSSim PLC1 program. ADR 0370 derived a law from the same source and
ADR 0371 refused it on the guard. ADR 0382 adopts the derived rule as the
candidate and asks for a guard type that holds both an exclusion list and an
equality, so the two forms can be compared without trying modes.

Import from here (`from phos.atlas.code_law import derive_valve_law`) rather
than from the submodules.

**The pipeline, in one line.** `read_pinned_source` reads three declared files of
the pinned ICSSim checkout, refusing any whose sha256 does not match;
`derive_valve_law` parses them into a `DerivedValveLaw` whose every number
carries the file and line it came from; `certified_breaks` evaluates a
`ControllerSample` against that law and returns each break with a certificate
showing the working; `check_agreement` reports ADR 0382's seven bars.

**What this subpackage does not do.**

- It does not import, execute or simulate the controller source. `ast.parse`
  builds a tree; no statement in it is ever run.
- It does not read ``data/phos-icssim-dev/roles.toml``, the hand-written
  quotation of the same source, because comparing a derivation against a
  transcription of itself proves nothing.
- It does not edit ``controller_valve``, move its literals, or hard-code the
  release literal to make a bar pass.
- It puts no confidence, probability, weight, magnitude or score on anything,
  and no type here has a field that could hold one.
- It does not place a derived law on the law page. A candidate is not a
  replacement; wiring one into the register needs a verdict that says kept.
"""

from __future__ import annotations

from phos.atlas.code_law.agreement import (
    BAR_NAMES,
    ENUMERATION_MODES,
    ENUMERATION_SEED,
    EXPECTED_CASE_COUNT,
    AgreementResult,
    BarResult,
    HandGuard,
    check_agreement,
    enumerate_samples,
    guard_forms_meet_bar,
    hand_guard,
)
from phos.atlas.code_law.certificate import (
    CertificateRow,
    CertifiedBreak,
    Disagreement,
    LawCertificate,
    certified_breaks,
    disagreement_certificate,
    plain,
)
from phos.atlas.code_law.derive import Derivation, derive_valve_law
from phos.atlas.code_law.law import (
    SAMPLE_FIELDS,
    DerivedBranch,
    DerivedCondition,
    DerivedForcedWrite,
    DerivedGuard,
    DerivedLiteral,
    DerivedRule,
    DerivedValveLaw,
    GuardForm,
    Side,
    sample_values,
)
from phos.atlas.code_law.source import (
    DECLARED_SOURCES,
    ICSSIM_COMMIT,
    DeclaredSource,
    PinnedSource,
    RefusalReason,
    SourceRead,
    SourceRefusal,
    SourceText,
    pinned_source_from_text,
    read_pinned_source,
)

__all__ = [
    "BAR_NAMES",
    "DECLARED_SOURCES",
    "ENUMERATION_MODES",
    "ENUMERATION_SEED",
    "EXPECTED_CASE_COUNT",
    "ICSSIM_COMMIT",
    "SAMPLE_FIELDS",
    "AgreementResult",
    "BarResult",
    "CertificateRow",
    "CertifiedBreak",
    "DeclaredSource",
    "Derivation",
    "DerivedBranch",
    "DerivedCondition",
    "DerivedForcedWrite",
    "DerivedGuard",
    "DerivedLiteral",
    "DerivedRule",
    "DerivedValveLaw",
    "Disagreement",
    "GuardForm",
    "HandGuard",
    "LawCertificate",
    "PinnedSource",
    "RefusalReason",
    "Side",
    "SourceRead",
    "SourceRefusal",
    "SourceText",
    "certified_breaks",
    "check_agreement",
    "derive_valve_law",
    "disagreement_certificate",
    "enumerate_samples",
    "guard_forms_meet_bar",
    "hand_guard",
    "pinned_source_from_text",
    "plain",
    "read_pinned_source",
    "sample_values",
]
