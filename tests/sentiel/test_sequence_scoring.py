"""Sequence scoring must reuse `phos.sentiel.sequences`' arithmetic, not a faster copy of it."""

from datetime import UTC, datetime, timedelta

import pytest

from phos.sentiel.sequence_scoring import (
    DECLARED_NGRAM,
    SEQUENCE_SWEEP,
    SequencePolicy,
    ngrams_of,
    score_day,
    train_population,
    train_self,
)
from phos.sentiel.sequences import sequence_surprise
from phos.sentiel.traces import DeclaredToken, EntityDayTrace

T = DeclaredToken


def _trace(user_id: str, index: int, *tokens: DeclaredToken) -> EntityDayTrace:
    return EntityDayTrace(
        user_id=user_id,
        day=datetime(2010, 1, 4, tzinfo=UTC) + timedelta(days=index),
        sequence=tokens,
        logons=1,
    )


ORDINARY = (T.LOGON, T.HTTP_REQUEST, T.FILE_ACCESS, T.LOGOFF)
RARE = (T.LOGON_OFF_HOURS, T.DEVICE_CONNECT, T.FILE_ACCESS, T.EMAIL_EXTERNAL)


class TestTheArithmeticIsTheModuleItWires:
    def test_gram_surprise_equals_sequences_sequence_surprise(self) -> None:
        """A performance change must not become a semantic one."""
        traces = [_trace("A", index, *ORDINARY) for index in range(20)]
        trained = train_population(traces, SequencePolicy(n=3))
        grams = [gram for trace in traces for gram in ngrams_of(trace.sequence, 3)]

        for gram in {("LOGON", "H", "F"), tuple(ORDINARY[:3][index].value for index in range(3))}:
            assert trained.surprise(gram) == pytest.approx(
                sequence_surprise(list(gram), [list(item) for item in grams])
            )

    def test_a_day_score_is_a_mean_not_a_sum(self) -> None:
        """A sum would grow with volume, and volume is already measured four ways.

        Built from a cycle the training set contains whole, so a longer day introduces no gram
        the model has not seen — the only thing that changes is how many of them there are. A
        sum would rise fivefold; a mean must not move.
        """
        cycle = (T.LOGON, T.HTTP_REQUEST, T.FILE_ACCESS, T.LOGOFF)
        traces = [_trace("A", index, *(cycle * 6)) for index in range(20)]
        trained = train_population(traces, SequencePolicy(n=2))
        short = trained.day_surprise(cycle * 1)
        long = trained.day_surprise(cycle * 5)
        assert long == pytest.approx(short, abs=0.25)


class TestWhatIsTrainedAndOnWhat:
    def test_a_rare_order_scores_higher_than_the_trained_one(self) -> None:
        traces = [_trace("A", index, *ORDINARY) for index in range(30)]
        trained = train_population(traces, SequencePolicy(n=DECLARED_NGRAM))
        assert trained.day_surprise(RARE) > trained.day_surprise(ORDINARY)

    def test_the_cut_is_read_off_the_training_days_only(self) -> None:
        traces = [_trace("A", index, *ORDINARY) for index in range(30)]
        trained = train_population(traces, SequencePolicy(alert_percentile=99.0))
        assert trained.training_days == 30
        assert trained.alert_cut == pytest.approx(trained.day_surprise(ORDINARY))

    def test_a_cold_start_entity_gets_no_self_baseline_at_all(self) -> None:
        """Unknown is not anomalous — `phos.sentiel.peers`' rule, one layer out."""
        traces = [_trace("BUSY", index, *ORDINARY) for index in range(10)]
        traces += [_trace("QUIET", 0, *ORDINARY)]
        baselines = train_self(traces, SequencePolicy(min_self_windows=8))
        assert "BUSY" in baselines
        assert "QUIET" not in baselines

    def test_a_day_with_no_self_baseline_reports_none_rather_than_zero(self) -> None:
        traces = [_trace("BUSY", index, *ORDINARY) for index in range(10)]
        trained = train_population(traces)
        scored = score_day(_trace("QUIET", 0, *RARE), trained, train_self(traces))
        assert scored.self_relative is None
        assert scored.population > 0.0


class TestTheOrderBlindBaselineTravelsBeside:
    def test_every_score_carries_the_count_baseline_it_must_beat(self) -> None:
        traces = [_trace("A", index, *ORDINARY) for index in range(20)]
        trained = train_population(traces)
        scored = score_day(_trace("A", 21, *RARE), trained)
        assert scored.count_baseline > 0.0
        assert scored.n_tokens == len(RARE)


class TestGrams:
    def test_a_sequence_shorter_than_n_is_padded_rather_than_dropped(self) -> None:
        grams = ngrams_of((T.LOGON,), 3)
        assert grams == [("L", "_", "_")]

    def test_an_empty_sequence_yields_nothing(self) -> None:
        assert ngrams_of((), 3) == []

    def test_a_non_positive_n_is_refused(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            ngrams_of((T.LOGON,), 0)


class TestTheSweepIsDeclared:
    def test_the_grid_is_a_declared_constant_rather_than_a_search(self) -> None:
        assert (DECLARED_NGRAM, 99.0) in SEQUENCE_SWEEP
        assert {n for n, _ in SEQUENCE_SWEEP} == {2, 3, 4}
        assert {pct for _, pct in SEQUENCE_SWEEP} == {95.0, 99.0, 99.9}
