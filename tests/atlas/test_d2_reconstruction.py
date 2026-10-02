"""D2 command reconstruction is completeness, not a lead rate."""

from __future__ import annotations

from pathlib import Path

from phos.atlas.command_reconstruction import (
    IssuerKind,
    reconstruction_completeness,
    reconstructions_from_attack_config,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ATTACKS = REPO_ROOT / "configs" / "attacks"


def test_unknown_master_config_reconstructs_four_engineering_writes() -> None:
    records = reconstructions_from_attack_config(ATTACKS / "08-water-unknown-master.toml")
    assert len(records) == 4
    assert all(record.issuer_kind is IssuerKind.UNKNOWN_MASTER for record in records)
    assert all(record.lead_rate is None for record in records)
    assert all(0.0 < reconstruction_completeness(record) < 1.0 for record in records)


def test_known_station_command_writes_are_not_unknown_master() -> None:
    records = reconstructions_from_attack_config(ATTACKS / "01-water-treatment-graded.toml")
    command_records = [
        record for record in records if record.function in {"ROGUE_COMMAND", "MIMIC_COMMAND"}
    ]
    assert command_records
    assert all(record.issuer_kind is IssuerKind.KNOWN_STATION for record in command_records)
    assert all(record.lead_rate is None for record in command_records)
