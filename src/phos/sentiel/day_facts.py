"""One person-day of facts the four lane-A streams share.

The 34-feature scorer is not used here. These fields come from the entity-day
trace and the LDAP role. Nothing in this module reads a label.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from phos.sentiel.traces import DeclaredToken

__all__ = ["COUNT_FIELDS", "DayFacts", "time_bucket"]


COUNT_FIELDS: tuple[str, ...] = (
    "logons",
    "off_hours_logons",
    "removable_connects",
    "file_accesses",
    "emails",
    "external_emails",
)


class DayFacts(BaseModel):
    """Identity and count facts for one user on one calendar day.

    Attributes:
        user_id: The corpus user id.
        day: Midnight UTC of the window.
        role: LDAP role, or ``unknown`` when the directory has none.
        logons: Logon events.
        off_hours_logons: Logons outside the declared working pattern.
        removable_connects: Removable-device connections.
        file_accesses: File-access events.
        emails: Messages sent.
        external_emails: Messages with any outside recipient.
        pcs: Distinct machines named in the window.
        hosts: Distinct web hosts requested.
        recipients: Distinct lowercased addresses mailed.
        sequence: Collapsed declared tokens in order.
    """

    model_config = ConfigDict(frozen=True)

    user_id: str = Field(min_length=1)
    day: datetime
    role: str = Field(min_length=1)
    logons: int = Field(default=0, ge=0)
    off_hours_logons: int = Field(default=0, ge=0)
    removable_connects: int = Field(default=0, ge=0)
    file_accesses: int = Field(default=0, ge=0)
    emails: int = Field(default=0, ge=0)
    external_emails: int = Field(default=0, ge=0)
    pcs: tuple[str, ...] = ()
    hosts: tuple[str, ...] = ()
    recipients: tuple[str, ...] = ()
    sequence: tuple[DeclaredToken, ...] = ()

    def count(self, field: str) -> int:
        """Return one of the six starter counts.

        Raises:
            KeyError: If ``field`` is not a starter count.
        """
        if field not in COUNT_FIELDS:
            raise KeyError(field)
        return int(getattr(self, field))


def time_bucket(day: DayFacts) -> str:
    """Return weekday/weekend crossed with on-hours/off-hours.

    Off-hours means the window recorded at least one off-hours logon. The
    trace has no event clock, so this is the only hour split that exists.
    """
    weekend = day.day.weekday() >= 5
    off = day.off_hours_logons > 0
    half = "we" if weekend else "wd"
    hours = "off" if off else "on"
    return f"{half}-{hours}"
