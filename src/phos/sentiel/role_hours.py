"""Role and time-of-day peers (ADR 0192).

A day is judged against people who share its LDAP role and its
weekday/weekend x on/off-hours bucket. ``peers.py`` is not edited.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from statistics import median

from pydantic import BaseModel, ConfigDict

from phos.sentiel.day_facts import DayFacts, time_bucket

__all__ = ["MIN_PEER_DAYS", "ROLE_HOUR_FIELDS", "RoleHourPeers"]

MIN_PEER_DAYS: int = 8
ROLE_HOUR_FIELDS: tuple[str, ...] = (
    "removable_connects",
    "external_emails",
    "file_accesses",
    "host_count",
)

_UNKNOWN_ROLE = "unknown"


class RoleHourPeers(BaseModel):
    """Peer median and MAD of four counts inside each ``(role, bucket)``.

    Attributes:
        medians: ``role -> bucket -> field -> median``.
        mads: ``role -> bucket -> field -> median absolute deviation``.
        sizes: ``role -> bucket -> training-day count``.
    """

    model_config = ConfigDict(frozen=True)

    medians: dict[str, dict[str, dict[str, float]]]
    mads: dict[str, dict[str, dict[str, float]]]
    sizes: dict[str, dict[str, int]]

    @classmethod
    def fit(cls, train: Sequence[DayFacts]) -> RoleHourPeers:
        """Fit medians from the attack-free prefix."""
        series: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(list))
        )
        sizes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for day in train:
            if day.role == _UNKNOWN_ROLE:
                continue
            bucket = time_bucket(day)
            sizes[day.role][bucket] += 1
            for field in ROLE_HOUR_FIELDS:
                series[day.role][bucket][field].append(_value(day, field))
        medians: dict[str, dict[str, dict[str, float]]] = {}
        mads: dict[str, dict[str, dict[str, float]]] = {}
        for role, buckets in series.items():
            medians[role] = {}
            mads[role] = {}
            for bucket, fields in buckets.items():
                medians[role][bucket] = {}
                mads[role][bucket] = {}
                for field, values in fields.items():
                    centre = float(median(values))
                    medians[role][bucket][field] = centre
                    mads[role][bucket][field] = float(
                        median([abs(item - centre) for item in values])
                    )
        sized = {role: dict(buckets) for role, buckets in sizes.items()}
        return cls(medians=medians, mads=mads, sizes=sized)

    def score(self, day: DayFacts) -> float:
        """Return the sum of positive peer-excess magnitudes."""
        if day.role == _UNKNOWN_ROLE:
            return 0.0
        bucket = time_bucket(day)
        if self.sizes.get(day.role, {}).get(bucket, 0) < MIN_PEER_DAYS:
            return 0.0
        total = 0.0
        for field in ROLE_HOUR_FIELDS:
            centre = self.medians[day.role][bucket][field]
            spread = self.mads[day.role][bucket][field]
            if spread <= 0.0:
                spread = 1.0
            excess = _value(day, field) - centre
            if excess > 0.0:
                total += excess / spread
        return total


def _value(day: DayFacts, field: str) -> float:
    if field == "host_count":
        return float(len(day.hosts))
    return float(day.count(field))
