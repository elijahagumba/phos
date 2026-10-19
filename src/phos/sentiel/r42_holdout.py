"""CERT r4.2, declared held out before any of its files is opened.

S3's larger release is r4.2. This module names that release and refuses both a
fetch and a score. It does not download an archive, it does not read a CSV, and
it does not compute a detection number. Peer-group advantage stays retired; this
declaration does not reopen it.
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
    """One release that a later session may score only after a new declaration.

    Attributes:
        dataset: Registry name of the corpus the release belongs to.
        release: The release id. For this declaration, ``r4.2``.
        role: ``held-out``. The files are not a development set.
        scored: Always false in the declaring session.
        homepage: The deposit page recorded for the dataset. Not a file URL.
        archive_hosts: Hosts the deposit's recorded files use. r4.2's own file
            id is not in the registry, so no file URL and no sha256 are invented.
    """

    dataset: str
    release: str
    role: str
    scored: bool
    homepage: str
    archive_hosts: tuple[str, ...]


#: Hosts the October build brief allows a lane to fetch from.
ALLOWED_FETCH_HOSTS: Final[tuple[str, ...]] = (
    "zenodo.org",
    "www.netresec.com",
    "github.com",
    "raw.githubusercontent.com",
    "media.githubusercontent.com",
    "pypi.org",
    "files.pythonhosted.org",
    "researchdata.tuwien.ac.at",
)

CERT_R42: Final[HeldOutRelease] = HeldOutRelease(
    dataset="cert-insider-threat",
    release="r4.2",
    role="held-out",
    scored=False,
    homepage="https://kilthub.cmu.edu/articles/dataset/Insider_Threat_Test_Dataset/12841247",
    archive_hosts=("kilthub.cmu.edu", "ndownloader.figshare.com"),
)
"""The larger CERT release, held out. Not scored, and not fetched."""


def r42_fetch_allowed() -> bool:
    """Return whether r4.2's recorded archive hosts are all on the allow-list.

    Returns:
        False while any recorded host sits outside `ALLOWED_FETCH_HOSTS`.
    """
    return all(host in ALLOWED_FETCH_HOSTS for host in CERT_R42.archive_hosts)


def r42_may_be_scored() -> bool:
    """Return whether this declaration permits a score.

    Returns:
        False. A held-out release is not scored in the session that declares it,
        including on a machine where the files happen to be present.
    """
    return False
