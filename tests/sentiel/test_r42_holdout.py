"""CERT r4.2 is named, held out, and neither fetched nor scored."""

from __future__ import annotations

from pathlib import Path

from phos.sentiel import r42_holdout
from phos.sentiel.r42_holdout import (
    ALLOWED_FETCH_HOSTS,
    CERT_R42,
    r42_fetch_allowed,
    r42_may_be_scored,
)


def test_r42_is_the_held_out_release() -> None:
    assert CERT_R42.dataset == "cert-insider-threat"
    assert CERT_R42.release == "r4.2"
    assert CERT_R42.role == "held-out"
    assert CERT_R42.scored is False


def test_r42_is_not_scored_even_as_a_call() -> None:
    assert r42_may_be_scored() is False


def test_the_archive_hosts_are_outside_the_allow_list() -> None:
    assert ALLOWED_FETCH_HOSTS == (
        "zenodo.org",
        "www.netresec.com",
        "github.com",
        "raw.githubusercontent.com",
        "media.githubusercontent.com",
        "pypi.org",
        "files.pythonhosted.org",
        "researchdata.tuwien.ac.at",
    )
    assert CERT_R42.archive_hosts == ("kilthub.cmu.edu", "ndownloader.figshare.com")
    assert r42_fetch_allowed() is False
    for host in CERT_R42.archive_hosts:
        assert host not in ALLOWED_FETCH_HOSTS


def test_the_declaration_module_does_not_fetch() -> None:
    source = Path(r42_holdout.__file__).read_text(encoding="utf-8")
    assert "urlopen" not in source
    assert "requests" not in source
    assert "httpx" not in source
