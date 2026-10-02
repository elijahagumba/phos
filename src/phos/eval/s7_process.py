"""Honesty helpers for the S7 campaign process table (Track A).

This module does **not** score the corpus. The shipped ``process_dataset.parquet`` (Zenodo
15373938) is 13,912 rows of control-centre telemetry with **no label column**. The textual
``normal`` / ``data_modification`` vocabulary lives on ``packets_dataset.parquet``, which is a
parsed packet **table**, not a pcap (ADR 0012 / 0040). Joining packet-row labels onto process
seconds is a later PART. Inventing attack windows, feeding parquet as capture, and adding an
S7comm dissector to chase a command row are all refused here.

``LabelledCsvAdapter`` is not extended. PyArrow is not a PHOS dependency: this module inspects
headers. Reading the parquet is a fetch-time inspection, not the detection path.

Invariants this module upholds:

* **Files win.** ADR 0033's "process parquet labels are textual" is false for the process file.
* **Unlabelled telemetry cannot support recall.** Prepare refuses rather than guessing.
* **``normal`` is not an attack** if those strings ever appear (the SWaT trap).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final, NoReturn

__all__ = [
    "NOT_A_COMMAND_CORPUS_CAVEAT",
    "PACKETS_ARE_NOT_PCAP_CAVEAT",
    "SHIPPED_MD5",
    "SHIPPED_N_ROWS",
    "SHIPPED_PROCESS_COLUMNS",
    "UNLABELLED_PROCESS_CAVEAT",
    "PrepareError",
    "is_data_modification",
    "label_columns",
    "prepare_labelled_track_a",
    "process_table_is_unlabelled",
    "require_shipped_process_schema",
]

SHIPPED_N_ROWS: Final = 13912
SHIPPED_MD5: Final = "ebc3e048e0319f044ea47cc08e498999"
SHIPPED_PROCESS_COLUMNS: Final[tuple[str, ...]] = (
    "archive_recv_ts",
    "in_pv_temp_air",
    "in_pv_wind_speed",
    "in_pv_poa_direct",
    "in_pv_poa_diffuse",
    "in_pv_cell_temperature",
    "in_pv_inverter_ac_power",
    "in_pv_inverter_dc_power",
    "in_batt_state_of_charge",
    "in_batt_voltage",
    "in_batt_current",
    "in_batt_actual_charge_power",
    "in_batt_temperature",
    "state_batt_voltage",
    "state_batt_current",
    "state_batt_state_of_charge",
    "state_batt_stored_energy",
    "out_pv_on_off",
    "out_pv_target_power",
    "out_batt_on_off",
    "out_batt_target_power",
)

_LABEL_NAMES: Final[frozenset[str]] = frozenset(
    {
        "label",
        "labels",
        "attack",
        "attack_active",
        "attack_phase",
        "attack_phase_all",
        "class",
        "marker",
        "att_flag",
        "target",
        "malicious",
    }
)

UNLABELLED_PROCESS_CAVEAT: Final = (
    "s7 process_dataset.parquet has no label column (ADR 0047). Textual "
    "normal/data_modification labels live on packets_dataset.parquet, which is a table "
    "not a pcap (ADR 0012). Do not invent process-row attack windows. Do not quote "
    "unlabelled telemetry as recall."
)

PACKETS_ARE_NOT_PCAP_CAVEAT: Final = (
    "packets_dataset.parquet is a parsed packet table. Feeding it as a pcap bypasses the "
    "dissector (ADR 0012). Atlas does not dissect S7comm."
)

NOT_A_COMMAND_CORPUS_CAVEAT: Final = (
    "Not a labelled command corpus (ADR 0040 / 0047). discover_labelled_command_corpora "
    "must stay empty."
)


class PrepareError(RuntimeError):
    """Raised when the S7 process table cannot support labelled Track A."""


def label_columns(header: Sequence[str]) -> tuple[str, ...]:
    """Return column names that would be attack labels if present.

    The shipped process table has none. ``out_pv_on_off`` is a plant actuator, not a label.
    """
    found: list[str] = []
    for name in header:
        key = str(name).strip().lower()
        if key in _LABEL_NAMES or key.endswith("_label"):
            found.append(str(name))
    return tuple(found)


def process_table_is_unlabelled(header: Sequence[str]) -> bool:
    """Return whether ``header`` carries no attack-label column."""
    return not label_columns(header)


def is_data_modification(value: object) -> bool:
    """Return whether a *packet-table* cell is the ``data_modification`` class.

    ``normal`` is not an attack. ``default_attack_when`` would read that string as one
    (the SWaT trap). This helper exists so a later join cannot silently invert the label.
    It is not evidence that the process table has these strings.
    """
    text = str(value).strip().lower()
    return text == "data_modification"


def require_shipped_process_schema(header: Sequence[str]) -> None:
    """Raise if ``header`` is not the shipped process schema, or if a label column appeared.

    Args:
        header: Column names from the process table (parquet or a conversion).

    Raises:
        PrepareError: If columns drifted, or a label column is present (ADR 0047 must be
            revisited before anyone scores recall).
    """
    names = tuple(str(column) for column in header)
    unexpected_labels = label_columns(names)
    if unexpected_labels:
        raise PrepareError(
            f"process table carries label column(s) {unexpected_labels}; "
            "ADR 0047 assumed none and must be revisited before Track A scoring"
        )
    if names != SHIPPED_PROCESS_COLUMNS:
        raise PrepareError(
            "process table columns are not the shipped Zenodo 15373938 schema "
            f"(got {len(names)} names, expected {len(SHIPPED_PROCESS_COLUMNS)})"
        )


def prepare_labelled_track_a(header: Sequence[str]) -> NoReturn:
    """Refuse to write a labelled CSV from this process table.

    Raises:
        PrepareError: Always, on the shipped unlabelled schema. If a label column is
            present, the error says ADR 0047 must be revisited rather than auto-scoring.
    """
    require_shipped_process_schema(header)
    raise PrepareError(UNLABELLED_PROCESS_CAVEAT)
