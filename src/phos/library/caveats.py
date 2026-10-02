"""Standing caveats for the dataset library. They travel with every catalogue and report.

The library is an *adversarial evaluation fixture*, not a public ICS or enterprise corpus.
Numbers measured on it describe how Atlas and Sentiel handle plants and organisations **we
designed**. They are not attack recall on HAI, BATADAL, distillation, or CERT, and they are
not a live-plant or live-SOC result. Constitution §3.5 and the cycle data gate still govern
any claim made on published data.
"""

from typing import Final

from phos.synth.attacks.spec import ATTACKS_ARE_OURS_CAVEAT
from phos.synth.plant import MODEL_NOT_REALITY_CAVEAT

__all__ = [
    "ATTACKS_ARE_OURS_CAVEAT",
    "LIBRARY_NOT_PUBLIC_DATA_CAVEAT",
    "MODEL_NOT_REALITY_CAVEAT",
    "PERSON_DAYS_ARE_OURS_CAVEAT",
    "SYNTHETIC_LIBRARY_CAVEATS",
]

LIBRARY_NOT_PUBLIC_DATA_CAVEAT: Final = (
    "THE DATASET LIBRARY IS NOT A PUBLIC CORPUS. It is generated from phos.synth plants and "
    "from hand-declared person-day personas. A detection rate measured here is an upper bound "
    "on this library, never a lower bound on reality, and it must not be quoted as HAI, "
    "BATADAL, batch-distillation, or CERT recall. Perturbation recall on distillation is a "
    "different ruler and is not this one. Public-data claims still require a confirmed licence "
    "and a harness row on that corpus."
)

PERSON_DAYS_ARE_OURS_CAVEAT: Final = (
    "THE IT PERSONAS ARE BEHAVIOURAL FIXTURES WE WROTE. They emit ontology Observations "
    "(counts of logons, files, hosts, devices) with entity-scoped labels. They are not malware, "
    "not credential-theft tooling, and not a live directory. Sentiel catching a labelled "
    "'insider_multi' user shows the scoring policy ranks the fixture we built, not that a SOC "
    "would catch a real insider. Peer-relative advantage on CERT remains unmeasured until a "
    "labelled peer-relative positive exists on that corpus (ADR 0023)."
)

SYNTHETIC_LIBRARY_CAVEATS: Final = (
    LIBRARY_NOT_PUBLIC_DATA_CAVEAT,
    MODEL_NOT_REALITY_CAVEAT,
    ATTACKS_ARE_OURS_CAVEAT,
    PERSON_DAYS_ARE_OURS_CAVEAT,
)
