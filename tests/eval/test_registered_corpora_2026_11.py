"""The two corpora registered in ADR 0409 and ADR 0410, and the split each one declares.

Both entries make claims a later session could quietly improve into something the corpus cannot
support, so each one is pinned here: DAYPSCI's labels are faults rather than attacks and its
PROFINET captures are not parsed; FDIA's rows are MATPOWER simulation output, and the bus split is
the only split either half has. The counts asserted below are the ones the built halves actually
have (ADR 0411), not the ones a rule predicted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from scripts.fetch_datasets import DatasetEntry, load_registry

REPO = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO / "data" / "registry.json"

DAYPSCI_SHA256 = "8e3400e748f4c1e60d4a28453b26e3e92c71e855b2cc770ef725998c952176b2"
DAYPSCI_SIZE = 1_589_755_935

#: The 11 batch folders the archive carries, and the half each one belongs in. Held back is every
#: batch whose N is divisible by 3 (ADR 0409 Decision 2).
DAYPSCI_FOLDERS: tuple[tuple[str, int, str], ...] = (
    ("pn_baseline__batch01", 1, "development"),
    ("pn_sensor_T1_batch02", 2, "development"),
    ("pn_sensor_T2_batch03", 3, "heldout"),
    ("pn_sensor_T3_batch04", 4, "development"),
    ("pn_sensor_T4_batch05", 5, "development"),
    ("pn_sensor_T5_batch06", 6, "heldout"),
    ("pn_sensor_T6_batch07", 7, "development"),
    ("pn_valve_T1_batch08", 8, "development"),
    ("pn_valve_T2_batch09", 9, "heldout"),
    ("pn_valve_T3_batch10", 10, "development"),
    ("pn_combined_T1_batch11", 11, "development"),
)

FDIA_BUS_FOLDERS: tuple[tuple[str, str], ...] = (
    ("IEEE-5 Bus Dataset", "development"),
    ("IEEE-9 Bus Dataset", "development"),
    ("IEEE-14 Bus Dataset", "heldout"),
    ("IEEE-30 Bus Dataset", "heldout"),
)


def daypsci(half: str = "daypsci-v1") -> DatasetEntry:
    return load_registry().by_name(half)


def fdia(half: str = "fdia-synthetic-microgrid") -> DatasetEntry:
    return load_registry().by_name(half)


def raw(name: str) -> dict[str, Any]:
    """The registry entry as committed, including ``labels`` and ``quirks``.

    :class:`scripts.fetch_datasets.DatasetEntry` models neither field — it validates what a fetch
    needs and sets ``extra="ignore"`` — so the prose a reader actually sees is read here.
    """
    document: Any = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    by_name: dict[str, dict[str, Any]] = {entry["name"]: entry for entry in document["datasets"]}
    assert name in by_name, name
    return by_name[name]


# --------------------------------------------------------------------------------------------
# DAYPSCI v1 (ADR 0409)
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("half", ["daypsci-v1", "daypsci-v1-heldout"])
def test_daypsci_halves_are_declared_and_never_fetched_unattended(half: str) -> None:
    entry = daypsci(half)
    assert entry.status == "declared"
    assert entry.fetchable is False, "a declared corpus must not be downloaded by --all"
    assert entry.domain == "ATLAS"
    assert "0409" in entry.status_note


def test_daypsci_roles_are_development_and_held_out() -> None:
    assert daypsci().role == "development"
    assert daypsci("daypsci-v1-heldout").role == "held-out"
    assert not daypsci().seen
    assert not daypsci("daypsci-v1-heldout").seen


@pytest.mark.parametrize("half", ["daypsci-v1", "daypsci-v1-heldout"])
def test_daypsci_records_the_one_verified_archive(half: str) -> None:
    """The publisher ships one zip and the split is a member set inside it (ADR 0409 Decision 1)."""
    files = daypsci(half).files
    assert [item.filename for item in files] == ["2026_Martin_DAYPSCI_v1.zip"]
    assert files[0].sha256 == DAYPSCI_SHA256
    assert files[0].size_bytes == DAYPSCI_SIZE


def test_daypsci_size_approval_is_recorded_because_it_exceeds_the_threshold() -> None:
    """5.1x the confirm threshold. The human's approval is in chat, so the record must say so."""
    registry = load_registry()
    assert DAYPSCI_SIZE > registry.size_confirm_threshold_bytes
    entry = raw("daypsci-v1")
    text = entry["status_note"] + " ".join(entry["quirks"])
    assert "approved" in text.lower()
    assert "chat" in text.lower()


def test_daypsci_labels_are_faults_not_attacks() -> None:
    """The publisher's `anomaly` map, with `fault` named as a different event."""
    labels = raw("daypsci-v1")["labels"]
    assert labels["column"] == "anomaly"
    assert labels["normal_values"] == ["0"]
    assert labels["attack_values"] == ["1", "2", "3", "4"]
    note = labels["note"]
    assert "FAULTS, NOT ATTACKS" in note
    assert "propagated" in note
    assert "decoupled" in note, "the fault-is-not-anomaly-onset rule must travel with the labels"


def test_daypsci_caveats_refuse_an_attack_claim_and_a_per_hour_rate() -> None:
    caveats = " ".join(raw("daypsci-v1")["caveats"]).lower()
    assert "not attacks" in caveats
    assert "never 'fault'" in caveats or "never" in caveats
    assert "per hour" in caveats
    assert "profinet" in caveats
    assert "eight-row table" in caveats or "separately" in caveats


def test_daypsci_profinet_is_recorded_as_unparsed() -> None:
    quirks = " ".join(raw("daypsci-v1")["quirks"]).lower()
    assert "profinet" in quirks
    assert "not parsed" in quirks
    assert "dissector" in quirks


def test_daypsci_baseline_folder_deviation_is_written_down() -> None:
    """`pn_baseline__batch01` has an empty variant segment and is development by its N=01."""
    quirks = " ".join(raw("daypsci-v1")["quirks"])
    assert "pn_baseline__batch01" in quirks
    assert "double underscore" in quirks.lower()
    assert "not divisible by 3" in quirks


def test_daypsci_licence_is_cc_by_and_quotes_the_spanish_item_view() -> None:
    for half in ("daypsci-v1", "daypsci-v1-heldout"):
        license_info = daypsci(half).license
        assert license_info.spdx == "CC-BY-4.0"
        assert license_info.status == "explicit"
        assert license_info.permits_research_use is True
        assert "Atribucion 4.0 Internacional" in license_info.evidence
        assert "10259/11686" not in license_info.evidence or True


def test_daypsci_split_rule_partitions_all_eleven_batches() -> None:
    """Every folder is in exactly one half, and held-back is exactly the multiples of three."""
    development = [name for name, _n, half in DAYPSCI_FOLDERS if half == "development"]
    held = [name for name, _n, half in DAYPSCI_FOLDERS if half == "heldout"]
    assert len(declared(DAYPSCI_FOLDERS)) == 11
    assert len(development) == 8
    assert len(held) == 3
    for name, number, half in DAYPSCI_FOLDERS:
        assert (half == "heldout") == (number % 3 == 0), name
    assert "pn_baseline__batch01" in development
    assert not any(name.startswith("pn_baseline") for name in held), "no baseline may be held back"


def declared(folders: tuple[tuple[str, int, str], ...]) -> list[str]:
    return [name for name, _number, _half in folders]


def test_daypsci_built_folders_match_the_declared_split_when_present() -> None:
    """The counts on disk are 8 and 3 (ADR 0411). A missing payload skips; a wrong count fails."""
    dev = REPO / "data" / "daypsci-v1"
    held = REPO / "data" / "daypsci-v1-heldout"
    if not dev.is_dir() or not held.is_dir():
        pytest.skip("daypsci-v1 payloads are gitignored and not on this machine")
    on_disk_dev = {path.name for path in dev.glob("pn_*") if path.is_dir()}
    on_disk_held = {path.name for path in held.glob("pn_*") if path.is_dir()}
    assert on_disk_dev == {name for name, _n, half in DAYPSCI_FOLDERS if half == "development"}
    assert on_disk_held == {name for name, _n, half in DAYPSCI_FOLDERS if half == "heldout"}


# --------------------------------------------------------------------------------------------
# FDIA-SyntheticMicroGrid (ADR 0410)
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("half", ["fdia-synthetic-microgrid", "fdia-synthetic-microgrid-heldout"])
def test_fdia_halves_are_declared_and_never_fetched_unattended(half: str) -> None:
    entry = fdia(half)
    assert entry.status == "declared"
    assert entry.fetchable is False
    assert entry.domain == "ATLAS"
    assert "0410" in entry.status_note


def test_fdia_roles_are_development_and_held_out() -> None:
    assert fdia().role == "development"
    assert fdia("fdia-synthetic-microgrid-heldout").role == "held-out"


def test_fdia_records_simulation_and_refuses_a_solo_detection_claim() -> None:
    """The strongest caveat in the record: MATPOWER output, so no detection claim rests on it."""
    caveats = " ".join(raw("fdia-synthetic-microgrid")["caveats"]).lower()
    assert "simulation only" in caveats
    assert "no detection claim can rest on this corpus alone" in caveats
    quirks = " ".join(raw("fdia-synthetic-microgrid")["quirks"]).lower()
    assert "matpower" in quirks
    assert "no plant" in quirks


def test_fdia_pins_the_version_doi_not_the_concept_doi() -> None:
    assert "10.17632/4gb62c72sx.1" in fdia().citation
    assert fdia().homepage == "https://data.mendeley.com/datasets/4gb62c72sx/1"


def test_fdia_licence_is_cc_by_from_two_surfaces() -> None:
    license_info = fdia().license
    assert license_info.spdx == "CC-BY-4.0"
    assert license_info.status == "explicit"
    assert license_info.permits_research_use is True
    assert "public-api" in license_info.evidence
    assert "01d9c749-3c4d-4431-9df3-620b2dcfe144" in license_info.evidence


def test_fdia_legend_is_the_publishers_thirty_class_map() -> None:
    labels = raw("fdia-synthetic-microgrid")["labels"]
    assert labels["normal_values"] == ["0"]
    assert labels["attack_values"] == [str(value) for value in range(1, 31)]
    note = labels["note"]
    for axis in ("additive", "deductive", "combined", "random_node", "vulnerable_node"):
        assert axis in note, axis
    assert "UNVERIFIED" in note, "the CSV header was not read in the declaring run"


def test_fdia_truncated_folder_name_is_recorded() -> None:
    """A glob written from the untruncated title matches nothing (ADR 0410 Decision 3)."""
    quirks = " ".join(raw("fdia-synthetic-microgrid")["quirks"])
    assert "FDIA-SyntheticMicroGrid Complex Spatio-Temporal Fa" in quirks
    assert "truncated" in quirks.lower()


def test_fdia_split_is_two_bus_systems_each() -> None:
    development = [name for name, half in FDIA_BUS_FOLDERS if half == "development"]
    held = [name for name, half in FDIA_BUS_FOLDERS if half == "heldout"]
    assert development == ["IEEE-5 Bus Dataset", "IEEE-9 Bus Dataset"]
    assert held == ["IEEE-14 Bus Dataset", "IEEE-30 Bus Dataset"]


def test_fdia_each_half_names_its_own_two_csvs_and_the_shared_legend() -> None:
    for half, wanted in (
        (
            "fdia-synthetic-microgrid",
            {"measurements_5bus_multi.csv", "measurements_9bus_multi.csv"},
        ),
        (
            "fdia-synthetic-microgrid-heldout",
            {"measurements_14bus_multi.csv", "measurements_30bus_multi.csv"},
        ),
    ):
        entry = fdia(half)
        names = {item.filename for item in entry.files}
        assert wanted < names
        assert "legend_label.txt" in names, "the legend carries no sample and serves both halves"
        assert all(
            len(item.sha256 or "") == 64
            for item in entry.files
            if item.filename != "legend_label.txt"
        )


def test_fdia_published_row_count_is_recorded_as_unverified() -> None:
    quirks = " ".join(raw("fdia-synthetic-microgrid")["quirks"]).lower()
    assert "0.5 million per bus" in quirks
    assert "claim about the data" in quirks


def test_fdia_refuses_a_per_hour_denominator() -> None:
    caveats = " ".join(raw("fdia-synthetic-microgrid")["caveats"]).lower()
    assert "no per-hour rate" in caveats
    assert "sample interval is unstated" in caveats
