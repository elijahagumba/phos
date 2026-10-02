"""Read a CERT release once and cache every entity-day trace, so nothing else has to.

``scripts/evaluate_sentiel_baseline.py`` reads the corpus twice — once to fit, once to score — and
every capability built on top of PART 6B would read it again. This script reads it **once** and
writes `phos.sentiel.traces.EntityDayTrace` records that regenerate the featuriser's exact
observation stream, plus the two facts the featuriser discards: which counterparties an entity-day
touched, and in what order it acted.

**The cache does not get written unless the reader that built it is proved equivalent to the
authority.** `--verify-days` re-reads the first N days of the release through
`phos.sentiel.cert.CertReader` — the slow, authoritative path — and compares the traces field by
field against the fast path's. A disagreement aborts before a byte is written, because a cache that
is nearly right is worse than no cache at all: every number downstream would be wrong by an amount
nobody could see. The default is 7 days, which on r3.1 is about 600,000 rows through both readers.

Usage::

    python scripts/build_sentiel_trace_cache.py                  # verify 7 days, then build
    python scripts/build_sentiel_trace_cache.py --verify-days 0  # skip the proof (not for a report)
    python scripts/build_sentiel_trace_cache.py --until-day 2010-02-01   # a bounded smoke build
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:  # pragma: no cover - script bootstrap
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.sentiel.cert import CertReader, CertRelease  # noqa: E402
from phos.sentiel.entities import EntityCatalogue  # noqa: E402
from phos.sentiel.fast_intake import fast_trace_stream, traces_agree  # noqa: E402
from phos.sentiel.featurise import WorkingHours  # noqa: E402
from phos.sentiel.traces import trace_stream, write_traces  # noqa: E402

logger = logging.getLogger("build_sentiel_trace_cache")

DEFAULT_DATA_DIR: Final = REPO_ROOT / "data"
DEFAULT_OUT: Final = REPO_ROOT / "data" / "cert-insider-threat" / "r3.1-entity-day-traces.jsonl.gz"
DEFAULT_VERIFY_DAYS: Final = 7


def _first_day(release: CertRelease) -> datetime:
    """Return midnight UTC of the release's earliest logon, without reading the whole corpus."""
    import csv

    from phos.sentiel.cert import LOGON_SPEC

    with release.path_for(LOGON_SPEC).open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = [name.strip() for name in next(reader)]
        row = next(reader)
        stamp = datetime.strptime(row[header.index("date")].strip(), "%m/%d/%Y %H:%M:%S")
    return datetime(stamp.year, stamp.month, stamp.day, tzinfo=UTC)


def _verify(
    release: CertRelease,
    reader: CertReader,
    working_hours: WorkingHours,
    org_domains: frozenset[str],
    days: int,
) -> tuple[bool, str, int]:
    """Compare the fast reader against `CertReader` over the first ``days`` windows."""
    until = _first_day(release) + timedelta(days=days)
    logger.info("verifying the fast reader against CertReader for windows before %s", until.date())

    started = time.monotonic()
    fast = list(
        fast_trace_stream(
            release, reader.email_senders, working_hours, org_domains, until_day=until
        )
    )
    fast_seconds = time.monotonic() - started
    logger.info("  fast reader: %d trace(s) in %.1fs", len(fast), fast_seconds)

    started = time.monotonic()
    bounded = itertools.takewhile(lambda event: event.timestamp < until, reader.events())
    authority = list(trace_stream(bounded, working_hours, org_domains))
    slow_seconds = time.monotonic() - started
    logger.info("  authority:   %d trace(s) in %.1fs", len(authority), slow_seconds)

    agree, reason = traces_agree(fast, authority)
    speedup = slow_seconds / fast_seconds if fast_seconds > 0 else 0.0
    if agree:
        logger.info(
            "  AGREE on %d entity-day trace(s) over %d day(s); fast path is %.1fx",
            len(fast),
            days,
            speedup,
        )
    return agree, reason, len(fast)


def main(argv: list[str] | None = None) -> int:
    """Build the trace cache. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--release-dir", type=str, default="cert-insider-threat/r3.1")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--verify-days",
        type=int,
        default=DEFAULT_VERIFY_DAYS,
        help="days to re-read through CertReader and compare before writing; 0 skips the proof",
    )
    parser.add_argument(
        "--until-day",
        type=str,
        default=None,
        help="stop before this YYYY-MM-DD window: a smoke build, never a reported number",
    )
    arguments = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout
    )

    release = CertRelease.discover(arguments.data_dir / arguments.release_dir)
    catalogue = EntityCatalogue.from_ldap_directory(release.ldap_directory)
    org_domain = catalogue.dominant_email_domain()
    if not org_domain:
        logger.error("the LDAP directory carries no email addresses; 'external' is undefined")
        return 2
    org_domains = frozenset({org_domain})
    working_hours = WorkingHours()
    reader = CertReader.for_release(release)
    logger.info(
        "release %s | %d directory users | org mail domain %s | %d resolvable senders",
        release.name,
        len(catalogue.entities),
        org_domain,
        len(reader.email_senders),
    )

    verified = 0
    if arguments.verify_days > 0:
        agree, reason, verified = _verify(
            release, reader, working_hours, org_domains, arguments.verify_days
        )
        if not agree:
            logger.error("fast reader DISAGREES with CertReader; refusing to write a cache")
            logger.error("  %s", reason)
            return 3
    else:
        logger.warning(
            "--verify-days 0: the fast reader was NOT checked against CertReader. A cache built "
            "this way must not stand behind a reported number."
        )

    until_day: datetime | None = None
    if arguments.until_day:
        until_day = datetime.strptime(arguments.until_day, "%Y-%m-%d").replace(tzinfo=UTC)

    started = time.monotonic()
    traces = fast_trace_stream(
        release, reader.email_senders, working_hours, org_domains, until_day=until_day
    )
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    written = write_traces(traces, arguments.out)
    elapsed = time.monotonic() - started

    summary = {
        "release": release.name,
        "org_domain": org_domain,
        "directory_users": len(catalogue.entities),
        "resolvable_senders": len(reader.email_senders),
        "entity_day_traces": written,
        "seconds": round(elapsed, 1),
        "verified_days": arguments.verify_days,
        "verified_traces": verified,
        "until_day": arguments.until_day,
        "working_hours": working_hours.model_dump(mode="json"),
        "out": str(arguments.out),
        "bytes": arguments.out.stat().st_size,
    }
    sidecar = arguments.out.parent / (arguments.out.name.split(".")[0] + ".summary.json")
    sidecar.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    logger.info("done in %.0fs: %s", elapsed, json.dumps(summary))
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
