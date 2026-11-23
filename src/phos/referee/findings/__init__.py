"""Findings registry and regression suite (PART S8).

Every way the breaker beats Atlas becomes a permanent, reproducible finding, a regression test,
and a line in an honest public record.

Findings are stored as one JSON file per finding in a tracked directory — history is in version
control. Never delete a finding. Status changes append to a history list.

**S0 hard rules still apply:** nothing here imports or modifies `phos.atlas`. Everything is
simulated; development seeds only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from phos.breaker.genome import AttackGenome

__all__ = [
    "Finding",
    "FindingRegistry",
    "FindingStatus",
    "Severity",
]


class FindingStatus(str):
    """A finding's lifecycle: open, fixed, will-not-fix."""

    OPEN = "open"
    FIXED = "fixed"
    WILL_NOT_FIX = "will-not-fix"
    FIXED_NARROWLY = "fixed narrowly"


class Severity(str):
    """Severity: physical harm yes/no, stealthy yes/no."""

    HARM_STEALTHY = "harm=yes, stealthy=yes"
    HARM_NOT_STEALTHY = "harm=yes, stealthy=no"
    NO_HARM_STEALTHY = "harm=no, stealthy=yes"
    NO_HARM_NOT_STEALTHY = "harm=no, stealthy=no"


@dataclass(frozen=True)
class Finding:
    """One way the breaker beat Atlas.

    Attributes:
        id: SHA-256 hash of the finding's content — computed, never supplied.
        date: When the finding was first recorded.
        source: Which breaker round (or "manual") found it.
        plant_spec_hash: The plant spec's id, for replay.
        seed: The development seed used.
        attack_genome: The attack that slipped past.
        family: The plant family the attack was generated against, for replay.
        what_happened: Plain-language description of what the attack did.
        atlas_output: What Atlas reported (alerts, hypotheses, confidences) — serialised.
        why_missed: Free-text hypothesis, never guessed at as fact.
        physical_harm: Whether the attack caused a real physical effect.
        stealthy: Whether Atlas failed to alert, or alerted only with low confidence.
        status: One of FindingStatus.
        history: Status changes, oldest first. The last entry is current.
        fixed_commit: The commit that fixed it (only when status is fixed).
        generalisation: Variant results proving the fix generalises (only when fixed).
    """

    id: str
    date: str
    source: str
    plant_spec_hash: str
    seed: int
    family: str
    attack_genome: AttackGenome
    what_happened: str
    atlas_output: str
    why_missed: str
    physical_harm: bool
    stealthy: bool
    status: str
    history: list[dict[str, object]] = field(default_factory=list)
    fixed_commit: str | None = None
    generalisation: list[dict[str, object]] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        source: str,
        plant_spec_hash: str,
        seed: int,
        family: str,
        attack_genome: AttackGenome,
        what_happened: str,
        atlas_output: str,
        why_missed: str,
        physical_harm: bool,
        stealthy: bool,
    ) -> Finding:
        """Build a new finding with a fresh id and the 'open' status."""
        now = datetime.now(UTC).isoformat()
        content = {
            "source": source,
            "plant_spec_hash": plant_spec_hash,
            "seed": seed,
            "family": family,
            "attack_genome": _genome_to_dict(attack_genome),
            "what_happened": what_happened,
            "atlas_output": atlas_output,
            "why_missed": why_missed,
            "physical_harm": physical_harm,
            "stealthy": stealthy,
            "date": now,
        }
        finding_id = hashlib.sha256(
            json.dumps(
                {k: v for k, v in content.items() if k != "date"},
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return cls(
            id=finding_id,
            date=now,
            source=source,
            plant_spec_hash=plant_spec_hash,
            seed=seed,
            family=family,
            attack_genome=attack_genome,
            what_happened=what_happened,
            atlas_output=atlas_output,
            why_missed=why_missed,
            physical_harm=physical_harm,
            stealthy=stealthy,
            status=FindingStatus.OPEN,
            history=[
                {
                    "status": FindingStatus.OPEN,
                    "at": now,
                    "reason": "finding recorded",
                }
            ],
        )

    def to_dict(self) -> dict[str, object]:
        """Return this finding as a plain dict for JSON serialisation."""
        return {
            "id": self.id,
            "date": self.date,
            "source": self.source,
            "plant_spec_hash": self.plant_spec_hash,
            "seed": self.seed,
            "family": self.family,
            "attack_genome": _genome_to_dict(self.attack_genome),
            "what_happened": self.what_happened,
            "atlas_output": self.atlas_output,
            "why_missed": self.why_missed,
            "physical_harm": self.physical_harm,
            "stealthy": self.stealthy,
            "status": self.status,
            "history": self.history,
            "fixed_commit": self.fixed_commit,
            "generalisation": self.generalisation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Finding:
        """Rebuild a :class:`Finding` from a dictionary produced by :meth:`to_dict`."""
        return cls(
            id=data["id"],
            date=data["date"],
            source=data["source"],
            plant_spec_hash=data["plant_spec_hash"],
            seed=data["seed"],
            family=data["family"],
            attack_genome=_genome_from_dict(data["attack_genome"]),
            what_happened=data["what_happened"],
            atlas_output=data["atlas_output"],
            why_missed=data["why_missed"],
            physical_harm=data["physical_harm"],
            stealthy=data["stealthy"],
            status=FindingStatus(data["status"]),
            history=data.get("history", []),
            fixed_commit=data.get("fixed_commit"),
            generalisation=data.get("generalisation", []),
        )


def _genome_to_dict(g: AttackGenome) -> dict[str, object]:
    return {
        "technique": g.technique.value,
        "target_tags": list(g.target_tags),
        "start_time": g.start_time,
        "duration": g.duration,
        "intensity": g.intensity,
        "shape": g.shape.value,
        "layer": g.layer,
    }


def _genome_from_dict(d: dict[str, Any]) -> AttackGenome:
    from phos.breaker.genome import AttackShape, AttackTechnique

    return AttackGenome(
        technique=AttackTechnique(d["technique"]),
        target_tags=tuple(d["target_tags"]),
        start_time=d["start_time"],
        duration=d["duration"],
        intensity=d["intensity"],
        shape=AttackShape(d["shape"]),
        layer=d["layer"],
    )


class FindingRegistry:
    """Append-only store of findings: one JSON file per finding in a tracked directory.

    Never deletes a finding. Status changes append to the history list.
    """

    def __init__(self, directory: Path) -> None:
        """Create the registry, creating the directory if needed."""
        self._directory = directory
        self._directory.mkdir(parents=True, exist_ok=True)

    def _path(self, finding_id: str) -> Path:
        return self._directory / f"{finding_id}.json"

    def add(self, finding: Finding) -> None:
        """Record a new finding. Refuses if a finding with the same id already exists."""
        path = self._path(finding.id)
        if path.exists():
            raise ValueError(f"finding {finding.id} already exists; findings are append-only")
        path.write_text(json.dumps(finding.to_dict(), indent=2) + "\n", encoding="utf-8")

    def get(self, finding_id: str) -> Finding | None:
        """Return a finding by id, or None if it does not exist."""
        path = self._path(finding_id)
        if not path.exists():
            return None
        return Finding.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_open(self) -> list[Finding]:
        """Return all open findings, newest first."""
        return [f for f in self._all() if f.status == FindingStatus.OPEN]

    def list_all(self) -> list[Finding]:
        """Return every finding, newest first."""
        return list(self._all())

    def _all(self) -> list[Finding]:
        findings: list[Finding] = []
        for path in sorted(self._directory.glob("*.json")):
            findings.append(Finding.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        findings.sort(key=lambda f: f.date, reverse=True)
        return findings

    def change_status(
        self,
        finding_id: str,
        new_status: str,
        reason: str,
        fixed_commit: str | None = None,
        generalisation: list[dict[str, object]] | None = None,
    ) -> None:
        """Change a finding's status, appending to its history.

        Refuses to mark "fixed" without generalisation evidence (a fix that only works on
        the exact original case is "fixed narrowly" and flagged).
        """
        finding = self.get(finding_id)
        if finding is None:
            raise ValueError(f"no such finding: {finding_id}")
        now = datetime.now(UTC).isoformat()

        if new_status == FindingStatus.FIXED and not generalisation:
            # A fix without variant evidence is "fixed narrowly", flagged.
            new_status = FindingStatus.FIXED_NARROWLY

        entry: dict[str, object] = {
            "status": new_status,
            "at": now,
            "reason": reason,
        }
        if fixed_commit:
            entry["commit"] = fixed_commit

        new_history = [*finding.history, entry]
        updated = Finding(
            id=finding.id,
            date=finding.date,
            source=finding.source,
            plant_spec_hash=finding.plant_spec_hash,
            seed=finding.seed,
            family=finding.family,
            attack_genome=finding.attack_genome,
            what_happened=finding.what_happened,
            atlas_output=finding.atlas_output,
            why_missed=finding.why_missed,
            physical_harm=finding.physical_harm,
            stealthy=finding.stealthy,
            status=new_status,
            history=new_history,
            fixed_commit=fixed_commit or finding.fixed_commit,
            generalisation=generalisation or finding.generalisation,
        )
        self._path(finding.id).write_text(
            json.dumps(updated.to_dict(), indent=2) + "\n", encoding="utf-8"
        )


_SEVERITY_ENV_VAR: Final = "PHOS_SEEDS_PRIVATE"


def severity_for(physical_harm: bool, stealthy: bool) -> Severity:
    """Return the severity label for a finding."""
    harm = "yes" if physical_harm else "no"
    stealth = "yes" if stealthy else "no"
    return Severity(f"harm={harm}, stealthy={stealth}")


__all__ = ["Finding", "FindingRegistry", "FindingStatus", "Severity", "severity_for"]
