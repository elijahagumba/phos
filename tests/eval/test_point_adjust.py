"""Point-adjusted F1 on hand-built segments. No corpus."""

from phos.eval.point_adjust import point_adjusted_f1


def test_one_hit_marks_the_whole_attack_segment() -> None:
    truth = [False, False, False, True, True, True, True, False, False, False]
    predicted = [False, False, False, True, False, False, False, False, False, False]
    result = point_adjusted_f1(truth, predicted)
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1 == 1.0


def test_a_miss_scores_zero() -> None:
    truth = [False, False, False, True, True, True, True, False, False, False]
    predicted = [True, False, False, False, False, False, False, False, False, False]
    result = point_adjusted_f1(truth, predicted)
    assert result.precision == 0.0
    assert result.recall == 0.0
    assert result.f1 == 0.0


def test_lengths_must_match_and_an_empty_series_is_zero() -> None:
    assert point_adjusted_f1([], []).f1 == 0.0
    try:
        point_adjusted_f1([True], [])
    except ValueError as error:
        assert "equal lengths" in str(error)
    else:
        raise AssertionError("unequal lengths were accepted")
