"""Entity-scoped ground truth: *which user* was malicious, and when.

This is the module the rest of Sentiel's honesty rests on.

PART 2's `LabelledInterval` says "the corpus was under attack between these two instants". For an
industrial plant that is the whole truth: an attacker manipulating a pump is attacking *the plant*,
and any alert in that window is about the same event. For an organisation it is not the truth at
all. When CERT says user ``CSF0929`` was malicious through July 2010, an alert about user
``ABC1234`` on the 14th of July is **wrong** — it names an innocent person — yet a time-only
matcher scores it as a hit, and does so for every one of the other 999 users in the corpus.

The size of that error is worth stating: r3.1 labels 2 malicious users out of 1000. A detector that
alerted on every user every day would score a perfect time-only recall while being wrong 99.8% of
the time. Flattening entity-scoped truth to a time window does not merely lose precision — it makes
the corpus unable to distinguish a working detector from a broken one.

So `EntityLabelledInterval` carries the user alongside the window and never loses it.
`as_labelled_interval` exists to hand a *single user's* windows to PART 2's metric math — which is
correct, because within one user's slice of the corpus time-only matching and entity-scoped
matching agree exactly. That is the seam `phos.sentiel.evaluation` is built on.
"""

import csv
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, model_validator

from phos.eval import LabelledInterval
from phos.ontology import UtcDatetime

__all__ = [
    "INSIDERS_FILENAME",
    "INSIDER_LABEL",
    "EntityLabelledInterval",
    "malicious_user_ids",
    "read_insiders",
]

logger = logging.getLogger(__name__)

INSIDERS_FILENAME: Final = "insiders.csv"
"""The master ground-truth file inside CERT's ``answers`` archive.

Its own readme calls it "the master file of true positives": one row per incident, giving the
release, the red-team scenario number, the username, and the start and end of the malicious
activity. The per-incident observable files beside it list the individual malicious events; this
PART labels at the incident level, which is the granularity an insider case is actually triaged at.
"""

INSIDER_LABEL: Final = "insider"

_ANSWERS_TIMESTAMP_FORMATS: Final = ("%m/%d/%Y %H:%M:%S",)
"""``insiders.csv`` mixes zero-padded and unpadded months across releases — ``3/6/2010`` on one row
and ``07/01/2010`` on the next. One ``strptime`` format reads both, so no inference is needed."""


class EntityLabelledInterval(BaseModel):
    """Ground truth that a named user behaved maliciously across a window of time.

    Attributes:
        user_id: The corpus's own identifier for the malicious user, e.g. ``"CSF0929"``.
        start: First instant of the malicious window, UTC, inclusive.
        end: Last instant, UTC, inclusive.
        label: Ground-truth class. ``"insider"`` throughout; the field exists so the type reads
            like PART 2's `LabelledInterval` beside it.
        scenario: The red-team scenario number from ``insiders.csv``, e.g. ``"1"``. Kept because
            the scenarios test different behaviour and a per-scenario recall says far more than a
            pooled one once there are enough incidents to break down.
        release: The release the incident belongs to, e.g. ``"3.1"``.

    Invariants:
        ``start <= end``.
    """

    model_config = ConfigDict(frozen=True)

    user_id: str
    start: UtcDatetime
    end: UtcDatetime
    label: str = INSIDER_LABEL
    scenario: str | None = None
    release: str | None = None

    @model_validator(mode="after")
    def _check_bounds(self) -> Self:
        if self.start > self.end:
            raise ValueError(f"interval is inverted: {self.start} > {self.end}")
        return self

    def contains(self, user_id: str, timestamp: datetime) -> bool:
        """Return whether this label covers ``user_id`` at ``timestamp``.

        Both halves must match. A timestamp inside the window but belonging to another user is
        **not** covered — which is the entire point of the type.
        """
        return user_id == self.user_id and self.start <= timestamp <= self.end

    def as_labelled_interval(self) -> LabelledInterval:
        """Return the time-only PART 2 interval for this label.

        Warning:
            The user is dropped, so this is only sound when the resulting interval is matched
            against detections **already restricted to `user_id`**. `phos.sentiel.evaluation` is
            the only caller, and it partitions by user before it calls this. Using it on a mixed
            detection set reintroduces exactly the error this module exists to prevent.
        """
        return LabelledInterval(
            start=self.start,
            end=self.end,
            label=self.label,
            attack_type=f"scenario-{self.scenario}" if self.scenario else None,
        )


def read_insiders(path: Path, release: str | None = None) -> list[EntityLabelledInterval]:
    """Read CERT's ``insiders.csv`` into entity-scoped labels.

    Args:
        path: Either the ``insiders.csv`` file or the ``answers`` directory holding it.
        release: Keep only rows for this release, e.g. ``"r3.1"`` or ``"3.1"`` — the leading
            ``r`` is optional, because the archive names files ``r3.1-1.csv`` while the ``dataset``
            column inside says ``3.1``. ``None`` keeps every release.

    Returns:
        Labels sorted by start time then user, so a report lists incidents in the order they began.

    Raises:
        FileNotFoundError: If the file is absent.
        ValueError: If the header is missing a required column, a timestamp will not parse, or
            ``release`` matches no row — an empty label set would silently score every detector at
            zero recall while looking like a completed run.
    """
    source = path / INSIDERS_FILENAME if path.is_dir() else path
    if not source.is_file():
        raise FileNotFoundError(f"CERT ground truth not found at {source}")

    wanted = release.removeprefix("r") if release else None
    required = {"dataset", "scenario", "user", "start", "end"}

    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = [name.strip() for name in (reader.fieldnames or [])]
        missing = required - set(header)
        if missing:
            raise ValueError(
                f"{source}: missing required column(s) {', '.join(sorted(missing))}; "
                f"the file has: {', '.join(header) or '(no header)'}"
            )
        labels = [
            EntityLabelledInterval(
                user_id=row["user"].strip(),
                start=_parse(row["start"].strip(), source, "start"),
                end=_parse(row["end"].strip(), source, "end"),
                scenario=row["scenario"].strip() or None,
                release=row["dataset"].strip() or None,
            )
            for row in reader
            if wanted is None or row["dataset"].strip() == wanted
        ]

    if not labels:
        raise ValueError(
            f"{source}: no ground-truth rows for release {release!r}. Every metric computed "
            "against an empty label set is vacuous, so this is refused rather than reported."
        )
    labels.sort(key=lambda label: (label.start, label.user_id))
    logger.info(
        "read %d insider label(s) for release %s: %s",
        len(labels),
        release or "(all)",
        ", ".join(f"{label.user_id}/scenario-{label.scenario}" for label in labels),
    )
    return labels


def malicious_user_ids(labels: Sequence[EntityLabelledInterval]) -> frozenset[str]:
    """Return the distinct users any label names as malicious."""
    return frozenset(label.user_id for label in labels)


def _parse(text: str, source: Path, column: str) -> datetime:
    """Parse an ``insiders.csv`` timestamp as UTC, matching the activity logs' own convention."""
    for fmt in _ANSWERS_TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise ValueError(
        f"{source}: {column} value {text!r} matches none of "
        f"{', '.join(repr(fmt) for fmt in _ANSWERS_TIMESTAMP_FORMATS)}"
    )
