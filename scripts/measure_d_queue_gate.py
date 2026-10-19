"""The real-data gate named in ADR 0234. It does not open a corpus.

Running ``atlas-queue-v2:familiarity`` on the five judging corpora needs a one-look
exception in ``data-tiers.mdc``. This branch does not add that exception, so the
process exits before any file is read. v1's A3 stays 57 of 203 either way.
"""

from __future__ import annotations

MESSAGE = (
    "atlas-queue-v2:familiarity-gate is not authorised. "
    "ADR 0234 names the look and does not take it. No corpus is opened."
)


def main() -> None:
    """Refuse the gate. Do not open a judging corpus."""
    raise SystemExit(MESSAGE)


if __name__ == "__main__":
    main()
