"""Declared chain shapes score by rarity, not by named hosts."""

from datetime import UTC, datetime

from phos.sentiel.behaviour_chains import DECLARED_CHAINS, ChainSurprise, shape_present
from phos.sentiel.day_facts import DayFacts
from phos.sentiel.traces import DeclaredToken


def _day(seq: str, day: int = 1) -> DayFacts:
    return DayFacts(
        user_id="U",
        day=datetime(2010, 1, day, tzinfo=UTC),
        role="Sales",
        sequence=tuple(DeclaredToken(char) for char in seq),
    )


def test_device_file_external_mail_is_the_first_declared_shape() -> None:
    assert DECLARED_CHAINS[0] == (
        DeclaredToken.DEVICE_CONNECT,
        DeclaredToken.FILE_ACCESS,
        DeclaredToken.EMAIL_EXTERNAL,
    )
    present = (
        DeclaredToken.DEVICE_CONNECT,
        DeclaredToken.HTTP_REQUEST,
        DeclaredToken.FILE_ACCESS,
        DeclaredToken.EMAIL_EXTERNAL,
    )
    missing = (
        DeclaredToken.EMAIL_EXTERNAL,
        DeclaredToken.FILE_ACCESS,
        DeclaredToken.DEVICE_CONNECT,
    )
    assert shape_present(present, DECLARED_CHAINS[0])
    assert not shape_present(missing, DECLARED_CHAINS[0])


def test_a_rare_shape_outscores_a_common_one() -> None:
    common = [_day("DFX", day=index + 1) for index in range(20)]
    rare = [_day("HXD", day=21)]
    model = ChainSurprise.fit(common + rare)
    assert model.score(_day("HXD", day=30)) > model.score(_day("DFX", day=30))
    assert model.score(_day("L", day=30)) == 0.0
