"""Round-2 Kelmarsh files: 2018 trains, 2019-2022 scores (ADR 0165).

ADR 0152 still trains on 2016-2018 when those zips are loaded. This module
refuses 2016 and 2017 for the round-2 measurement, because 2017 is absent and
2016 on this machine is not the registry file. Held-back names stay closed.
"""

from __future__ import annotations

from typing import Final

from phos.eval.kelmarsh_log import refuse_held_back_name

__all__ = [
    "REFUSED_THIS_ROUND",
    "RESULT_NAME",
    "SCORED_SCADA_FILES",
    "assert_round2_zip",
    "decide_keep",
]

SCORED_SCADA_FILES: Final[tuple[str, ...]] = (
    "Kelmarsh_SCADA_2018_3084.zip",
    "Kelmarsh_SCADA_2019_3085.zip",
    "Kelmarsh_SCADA_2020_3086.zip",
    "Kelmarsh_SCADA_2021_4456.zip",
    "Kelmarsh_SCADA_2022_4457.zip",
)
REFUSED_THIS_ROUND: Final[tuple[str, ...]] = (
    "Kelmarsh_SCADA_2016_3082.zip",
    "Kelmarsh_SCADA_2017_3083.zip",
)
RESULT_NAME: Final = "lane-b-dev:kelmarsh-2018-2022"


def assert_round2_zip(filename: str) -> None:
    """Raise unless ``filename`` is one of the five scored year zips.

    Args:
        filename: The zip's final component.

    Raises:
        HeldBackFileError: If the name is held back.
        ValueError: If the name is 2016, 2017, or otherwise not scored here.
    """
    refuse_held_back_name(filename)
    if filename in REFUSED_THIS_ROUND or filename not in SCORED_SCADA_FILES:
        raise ValueError(f"{filename} is not opened by the 2018-2022 Kelmarsh run")


def decide_keep(
    current_per_shift: float | None,
    current_share: float | None,
    candidate_per_shift: float | None,
    candidate_share: float | None,
) -> str:
    """Return ``keep`` only when false alerts fall and the explained share holds.

    Args:
        current_per_shift: Unexplained alerts per shift of the kept scorer.
        current_share: Explained share of the kept scorer.
        candidate_per_shift: The same rate for the candidate.
        candidate_share: The same share for the candidate.

    Returns:
        ``keep`` or ``revert``.
    """
    if (
        current_per_shift is None
        or current_share is None
        or candidate_per_shift is None
        or candidate_share is None
    ):
        return "revert"
    if candidate_per_shift < current_per_shift and candidate_share + 1e-12 >= current_share:
        return "keep"
    return "revert"
