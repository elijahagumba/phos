"""`phos.referee.seeds`: four pool files, disjoint, retirement, and the sealed-family check."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.referee.sealed_fixture import SEALED_FAMILY, register

from phos.referee.seeds import (
    SeedEntry,
    SeedPool,
    SeedVault,
    SeedVaultError,
    assert_no_sealed_in_open_pools,
)


def _vault(tmp_path: Path) -> SeedVault:
    return SeedVault(
        {
            SeedPool.DEV: tmp_path / "dev.seedvault.json",
            SeedPool.PUBLIC: tmp_path / "public.seedvault.json",
            SeedPool.PRIVATE: tmp_path / "private.seedvault.json",
            SeedPool.RETIRED: tmp_path / "retired.seedvault.json",
        }
    )


def test_an_empty_pool_file_is_an_empty_tuple(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    assert vault.load(SeedPool.DEV) == ()


def test_add_then_load_round_trips(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    entries = [SeedEntry(family="level_flow", seed=1), SeedEntry(family="power", seed=2)]
    vault.add(SeedPool.DEV, entries)
    assert set(vault.load(SeedPool.DEV)) == set(entries)


def test_add_refuses_a_seed_already_in_another_pool(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    vault.add(SeedPool.DEV, [SeedEntry(family="level_flow", seed=1)])
    with pytest.raises(SeedVaultError, match="already lives in"):
        vault.add(SeedPool.PUBLIC, [SeedEntry(family="level_flow", seed=1)])


def test_check_disjoint_passes_on_a_clean_vault(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    vault.add(SeedPool.DEV, [SeedEntry(family="level_flow", seed=1)])
    vault.add(SeedPool.PRIVATE, [SeedEntry(family="level_flow", seed=2)])
    vault.check_disjoint()  # does not raise


def test_check_disjoint_catches_a_seed_written_into_two_files_by_hand(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    vault.add(SeedPool.DEV, [SeedEntry(family="level_flow", seed=1)])
    # Simulate a pool file edited by hand rather than through `add`, which is exactly the
    # situation `check_disjoint` exists to catch.
    vault._write(SeedPool.PUBLIC, [SeedEntry(family="level_flow", seed=1)])
    with pytest.raises(SeedVaultError, match="more than one pool"):
        vault.check_disjoint()


def test_retire_moves_entries_from_private_to_retired(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    entry = SeedEntry(family="level_flow", seed=99)
    vault.add(SeedPool.PRIVATE, [entry])

    vault.retire([entry])

    assert vault.load(SeedPool.PRIVATE) == ()
    assert vault.load(SeedPool.RETIRED) == (entry,)


def test_retire_refuses_an_entry_not_in_private(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    with pytest.raises(SeedVaultError, match="is not in the private pool"):
        vault.retire([SeedEntry(family="level_flow", seed=1)])


def test_retire_is_idempotent_for_an_already_retired_entry(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    entry = SeedEntry(family="level_flow", seed=1)
    vault.add(SeedPool.PRIVATE, [entry])
    vault.retire([entry])
    vault.add(SeedPool.PRIVATE, [SeedEntry(family="level_flow", seed=2)])
    vault.retire([SeedEntry(family="level_flow", seed=2)])

    assert len(vault.load(SeedPool.RETIRED)) == 2


def test_from_env_requires_all_four_variables(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("PHOS_SEEDS_DEV", raising=False)
    monkeypatch.delenv("PHOS_SEEDS_PUBLIC", raising=False)
    monkeypatch.delenv("PHOS_SEEDS_PRIVATE", raising=False)
    monkeypatch.delenv("PHOS_SEEDS_RETIRED", raising=False)
    monkeypatch.setenv("PHOS_SEEDS_DEV", str(tmp_path / "dev.seedvault.json"))

    with pytest.raises(SeedVaultError, match="not set"):
        SeedVault.from_env()


def test_no_sealed_family_may_live_in_dev_or_public(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An open (non-sealed) family in dev or public is fine; this is the negative case."""
    vault = _vault(tmp_path)
    vault.add(SeedPool.DEV, [SeedEntry(family="level_flow", seed=1)])
    monkeypatch.delenv("PHOS_SYNTH_ALLOW_SEALED", raising=False)
    assert_no_sealed_in_open_pools(vault)  # does not raise


def test_sealed_family_in_dev_pool_is_refused(tmp_path: Path) -> None:
    """A sealed seed sitting in an open pool is refused.

    The family is the fixture one rather than the real sealed family. The guard reads the
    ``sealed`` flag and nothing else, so naming the real family here only published its
    identifier, and that package is withheld from the public export in any case.
    """
    from phos.synth.families import SEALED_ENV_VAR

    register()
    vault = _vault(tmp_path)
    vault.add(SeedPool.DEV, [SeedEntry(family=SEALED_FAMILY, seed=1)])

    with pytest.raises(SeedVaultError, match="sealed"):
        assert_no_sealed_in_open_pools(vault)
    # The check must restore the environment exactly as it found it.
    import os

    assert SEALED_ENV_VAR not in os.environ
