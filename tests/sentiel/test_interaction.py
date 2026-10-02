"""Session S2: declared interaction structure, never clustered from who talks."""

from phos.sentiel import DeclaredCounterpartyDirectory, interaction_is_expected


def test_a_declared_role_pair_is_expected() -> None:
    directory = DeclaredCounterpartyDirectory(
        allowed={"Salesman": frozenset({"Salesman", "ITAdmin"})}
    )
    assert interaction_is_expected(directory, "Salesman", "ITAdmin") is True
    assert interaction_is_expected(directory, "Salesman", "Director") is False


def test_an_undeclared_role_is_insufficient_not_an_anomaly() -> None:
    directory = DeclaredCounterpartyDirectory(allowed={"Salesman": frozenset({"Salesman"})})
    assert interaction_is_expected(directory, "UnknownRole", "Salesman") is None
