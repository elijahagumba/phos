#!/usr/bin/env python3
"""Score the six identity features on one CERT release (ADR 0146, ADR 0204, ADR 0261).

``--register empty`` is the empty register named in ADR 0204. ``--register directory``
is every email address in that release's own LDAP snapshots (ADR 0261): hosts and
machines stay empty, and the address list is not written into the result. Neither
mode fills the register from a labelled day or puts a weight on the 34. The script
refuses to write over an existing result. ``insiders.csv`` is read only after the
feature summary exists, and only to count labelled insiders.

Usage: pass ``--release r3.1`` or ``r4.2`` and a required ``--out`` path.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:  # pragma: no cover - script bootstrap
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.sentiel.entities import EntityCatalogue  # noqa: E402
from phos.sentiel.identity_score import (  # noqa: E402
    EMPTY_REGISTER_SHA256,
    directory_destination_register,
    summarise_traces,
)
from phos.sentiel.labels import read_insiders  # noqa: E402
from phos.sentiel.named_counterparties import DeclaredIdentities, register_sha256  # noqa: E402
from phos.sentiel.traces import read_traces  # noqa: E402

# Hashes of the LDAP-email registers, computed from the directory files before
# this score reads insiders.csv. ADR 0261. A directory run on the real corpus
# must match. A fixture data directory is not checked against these.
DECLARED_DIRECTORY_SHA256: Final[dict[str, str]] = {
    "r3.1": "6bcb876c4d9887b2bec5d8b92826c6b18cf02b95b1b4dc069dc6e5b53c706f83",
    "r4.2": "6b0597ae973edb27f2ff995ab1727e7bf12ae6af6aae57ba17c54169d294aac0",
}

logger = logging.getLogger("score_identity_features")

DEFAULT_DATA: Final = REPO_ROOT / "data" / "cert-insider-threat"


def main(argv: list[str] | None = None) -> int:
    """Score one release and write the JSON. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", choices=("r3.1", "r4.2"), required=True)
    parser.add_argument(
        "--register",
        choices=("empty", "directory"),
        default="empty",
        help="empty is ADR 0204; directory is every LDAP email address (ADR 0261)",
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--cache", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)
    if arguments.out.exists():
        logger.error("%s already exists; this score is not run again", arguments.out)
        return 2

    started = time.monotonic()
    cache = arguments.cache or (
        arguments.data_dir / f"{arguments.release}-entity-day-traces.jsonl.gz"
    )
    if arguments.register == "empty":
        register: DeclaredIdentities | None = None
        expected = EMPTY_REGISTER_SHA256
        source = "empty"
        note = (
            "Empty. ADR 0146 forbids filling the register from a labelled day, "
            "and no other register was committed before this score."
        )
        counts = {"hosts": 0, "destinations": 0, "pcs": 0}
    else:
        catalogue = EntityCatalogue.from_ldap_directory(
            arguments.data_dir / arguments.release / "LDAP"
        )
        register = directory_destination_register(catalogue)
        expected = register_sha256(register)
        declared = DECLARED_DIRECTORY_SHA256[arguments.release]
        if arguments.data_dir.resolve() == DEFAULT_DATA.resolve() and expected != declared:
            logger.error(
                "directory register hash %s is not the hash declared for %s",
                expected,
                arguments.release,
            )
            return 1
        source = "ldap-email"
        note = (
            "Destinations are every email address in this release's LDAP snapshots. "
            "Hosts and machines are empty. The address list is not written here. "
            "insiders.csv was not read to choose the names."
        )
        counts = {"hosts": 0, "destinations": len(register.destinations), "pcs": 0}
    summary = summarise_traces(read_traces(cache), register)
    if summary["register_sha256"] != expected:
        logger.error("register hash %s is not %s", summary["register_sha256"], expected)
        return 1
    labels = read_insiders(arguments.data_dir / "answers", arguments.release)
    insiders = tuple(dict.fromkeys(label.user_id for label in labels))
    payload: dict[str, object] = {
        "release": arguments.release,
        "register_source": source,
        "register_counts": counts,
        "register_sha256": expected,
        "register_note": note,
        "features": summary["features"],
        "all_zero": summary["all_zero"],
        "destinations_named": summary["destinations_named"],
        "n_observations": summary["n_observations"],
        "n_labelled_insiders": len(insiders),
        "weights_on_the_34": None,
        "seconds": round(time.monotonic() - started, 1),
    }
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = arguments.out.with_suffix(arguments.out.suffix + ".partial")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(arguments.out)
    logger.info(
        "%s all_zero=%s observations=%s insiders=%d",
        arguments.release,
        summary["all_zero"],
        summary["n_observations"],
        len(insiders),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
