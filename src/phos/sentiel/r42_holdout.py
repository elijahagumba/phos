"""CERT r4.2, named before any of its files was opened (ADR 0147, ADR 0202).

This module names the release. It does not download an archive, it does not read
a CSV, and it does not compute a detection number. ADR 0202 permits a fetch from
the deposit hosts and permits one score. The score is not this module.
``CERT_R42.scored`` stays false until that shot is written. Peer-group advantage
stays retired.
"""

from __future__ import annotations

from typing import Final, NamedTuple

__all__ = [
    "ALLOWED_FETCH_HOSTS",
    "CERT_R42",
    "HeldOutRelease",
    "r42_fetch_allowed",
    "r42_may_be_scored",
]


class HeldOutRelease(NamedTuple):
    """One release that is scored only after the declaration that permits it.

    Attributes:
        dataset: Registry name of the corpus the release belongs to.
        release: The release id. For this declaration, ``r4.2``.
        role: ``held-out``. The files are not a development set.
        scored: False until the one shot ADR 0202 names has been written.
        homepage: The deposit page recorded for the dataset. Not a file URL.
        archive_hosts: Hosts the deposit's recorded files use. ADR 0202 puts both
            on the allow-list. This tuple does not itself fetch.
    """

    dataset: str
    release: str
    role: str
    scored: bool
    homepage: str
    archive_hosts: tuple[str, ...]


#: Hosts a lane may fetch from. ``kilthub.cmu.edu`` and ``ndownloader.figshare.com``
#: were added by ADR 0202 so the registered r4.2 archive can be fetched.
ALLOWED_FETCH_HOSTS: Final[tuple[str, ...]] = (
    "zenodo.org",
    "www.netresec.com",
    "github.com",
    "raw.githubusercontent.com",
    "media.githubusercontent.com",
    "pypi.org",
    "files.pythonhosted.org",
    "researchdata.tuwien.ac.at",
    "kilthub.cmu.edu",
    "ndownloader.figshare.com",
)

CERT_R42: Final[HeldOutRelease] = HeldOutRelease(
    dataset="cert-insider-threat",
    release="r4.2",
    role="held-out",
    scored=False,
    homepage="https://kilthub.cmu.edu/articles/dataset/Insider_Threat_Test_Dataset/12841247",
    archive_hosts=("kilthub.cmu.edu", "ndownloader.figshare.com"),
)
"""The larger CERT release. Fetch and one score are permitted by ADR 0202. Not yet scored."""


def r42_fetch_allowed() -> bool:
    """Return whether r4.2's recorded archive hosts are all on the allow-list.

    Returns:
        True once every recorded host is in `ALLOWED_FETCH_HOSTS` (ADR 0202).
    """
    return all(host in ALLOWED_FETCH_HOSTS for host in CERT_R42.archive_hosts)


def r42_may_be_scored() -> bool:
    """Return whether ADR 0202 permits the one r4.2 score.

    Returns:
        True. This function does not read a file and does not compute a score.
        ``CERT_R42.scored`` stays false until that shot has been written.
    """
    return True
