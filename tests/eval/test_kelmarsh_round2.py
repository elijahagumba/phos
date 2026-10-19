"""Round-2 Kelmarsh refuses 2016 and 2017, and keeps a quieter explained score."""

from datetime import UTC, datetime

import numpy
import pytest

from phos.eval.kelmarsh_log import HeldBackFileError
from phos.eval.kelmarsh_modes import (
    CURTAIL_PITCH_DEG,
    label_modes,
)
from phos.eval.kelmarsh_round2 import (
    REFUSED_THIS_ROUND,
    SCORED_SCADA_FILES,
    assert_round2_zip,
    decide_keep,
)


def test_round2_opens_only_2018_through_2022() -> None:
    assert SCORED_SCADA_FILES[0].startswith("Kelmarsh_SCADA_2018")
    assert SCORED_SCADA_FILES[-1].startswith("Kelmarsh_SCADA_2022")
    for name in SCORED_SCADA_FILES:
        assert_round2_zip(name)
    for name in REFUSED_THIS_ROUND:
        with pytest.raises(ValueError):
            assert_round2_zip(name)
    with pytest.raises(HeldBackFileError):
        assert_round2_zip("Kelmarsh_SCADA_2023_5961.zip")


def test_keep_needs_fewer_false_alerts_and_no_lost_explanations() -> None:
    assert decide_keep(2.0, 0.4, 1.0, 0.4) == "keep"
    assert decide_keep(2.0, 0.4, 1.0, 0.39) == "revert"
    assert decide_keep(2.0, 0.4, 2.0, 0.9) == "revert"
    assert decide_keep(None, 0.4, 1.0, 0.5) == "revert"


def test_idle_curtailment_and_the_three_startup_rows() -> None:
    rows = [
        (1.0, 0.0, 0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0, 0.0, 0.0),
        (8.0, 400.0, 10.0, 10.0, 1.0),
        (8.0, 500.0, 10.0, 10.0, 1.0),
        (8.0, 500.0, 10.0, 10.0, 1.0),
        (8.0, 500.0, 10.0, 10.0, 1.0),
        (8.0, 200.0, 10.0, 10.0, CURTAIL_PITCH_DEG),
        (8.0, 200.0, 10.0, 10.0, CURTAIL_PITCH_DEG),
        (8.0, 500.0, 10.0, 10.0, 1.0),
        (8.0, 500.0, 10.0, 10.0, 1.0),
        (8.0, 500.0, 10.0, 10.0, 1.0),
        (1.0, 0.0, 0.0, 0.0, 90.0),
    ]
    labels = label_modes(numpy.asarray(rows, dtype=numpy.float64))
    assert list(labels[:2]) == [0, 0]
    assert list(labels[2:5]) == [3, 3, 3]
    assert labels[5] == 1
    assert list(labels[6:8]) == [2, 2]
    assert list(labels[8:11]) == [4, 4, 4]
    assert labels[11] == 0
    assert datetime(2018, 1, 1, tzinfo=UTC).year == 2018
