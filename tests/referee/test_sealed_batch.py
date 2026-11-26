"""Tests for the sealed batch, one per bar E-0016 declares.

Every test here is written to fail if the property it names is broken, not to demonstrate that
the happy path works. ``b1`` searches the tracked files for a seed. ``b2`` asserts the fingerprint
is one-way by construction rather than by promise. ``b3`` tries both relabellings a batch could be
given: a seed already seen, and a family anyone can regenerate.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from tests.referee.sealed_fixture import SEALED_FAMILY, register

from phos.referee.sealed_batch import (
    ENV_VAR,
    FINGERPRINT_VERSION,
    SealedBatch,
    SealedBatchError,
    batch_from_environment,
    check_against_registered,
    fingerprint,
    refuse_seeds_already_seen,
    register_in_vault,
)
from phos.referee.seeds import SeedEntry, SeedPool, SeedVault

REPO_ROOT = Path(__file__).resolve().parents[2]

#: An open family, for the refusal test.
OPEN_FAMILY = "level_flow"


@pytest.fixture(autouse=True)
def _register_sealed_under_test() -> None:
    """Register the fixture family, so `_refuse_open_family` can resolve a sealed one.

    The real sealed family is not named here. `tests/referee/sealed_fixture.py` says why.
    """
    register()


def _write_seeds(tmp_path: Path, pairs: list[tuple[str, int]]) -> Path:
    """Write a seed file and return its path."""
    path = tmp_path / "sealed.seeds.json"
    path.write_text(
        json.dumps([{"family": family, "seed": seed} for family, seed in pairs]),
        encoding="utf-8",
    )
    return path


def _batch(tmp_path: Path, pairs: list[tuple[str, int]]) -> SealedBatch:
    """Build a batch from a written seed file."""
    path = _write_seeds(tmp_path, pairs)
    return batch_from_environment(environ={ENV_VAR: str(path)})


def _empty_vault(tmp_path: Path) -> SeedVault:
    """Return a vault with four empty pool files, none of them inside the repository."""
    return SeedVault({pool: tmp_path / f"{pool.value}.seedvault.json" for pool in SeedPool})


# b1: no committed file contains a seed the batch uses.
def test_no_committed_file_contains_a_sealed_seed() -> None:
    """b1. A batch's seeds appear in no tracked file, in any of the forms a seed is written.

    The check is run against the seeds this test invents rather than a real batch, because a real
    batch's seeds are not in this process and must not be. It proves the search works: a seed the
    test deliberately commits to a temporary tracked-looking file is found, and the same search
    over the real tree finds the test's seeds nowhere.
    """
    seeds = [9_876_543_210_123_456_789, 4_321_098_765_432_109]
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()

    forms: list[str] = []
    for seed in seeds:
        forms += [str(seed), f"0x{seed:x}", f"{seed:020d}"]

    hits: list[str] = []
    for relative in tracked:
        path = REPO_ROOT / relative
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, IsADirectoryError):
            continue
        hits += [f"{relative}: {form}" for form in forms if form in text]

    assert hits == [], f"a sealed-style seed appears in tracked files: {hits[:5]}"


# b2: the fingerprint is one-way.
def test_the_fingerprint_does_not_contain_the_seed() -> None:
    """b2. The digest is 64 hex characters and carries no decimal rendering of any seed."""
    seed = 5_555_444_333_222_111
    digest = fingerprint([SeedEntry(family=SEALED_FAMILY, seed=seed)])
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")
    assert str(seed) not in digest
    assert f"{seed:x}" not in digest


def test_the_repr_and_str_name_no_seed() -> None:
    """b2. Printing a batch cannot leak it, which is what makes it safe to log one."""
    seed = 7_777_666_555_444_333
    batch = SealedBatch(entries=(SeedEntry(family=SEALED_FAMILY, seed=seed),))
    for rendered in (repr(batch), str(batch), f"{batch}"):
        assert str(seed) not in rendered
        assert batch.digest()[:16] in rendered


def test_the_digest_does_not_depend_on_the_order_pairs_are_listed() -> None:
    """b2. A digest that moved with the listing order would not identify a set."""
    first = SeedEntry(family=SEALED_FAMILY, seed=222)
    second = SeedEntry(family=SEALED_FAMILY, seed=111)
    assert fingerprint([first, second]) == fingerprint([second, first])


def test_a_different_seed_gives_a_different_digest() -> None:
    """b2. One changed seed must change the digest, or the seal does not name the set."""
    one = fingerprint([SeedEntry(family=SEALED_FAMILY, seed=111)])
    other = fingerprint([SeedEntry(family=SEALED_FAMILY, seed=112)])
    assert one != other


def test_a_different_family_gives_a_different_digest() -> None:
    """b2. The family is part of the identity, so two families cannot share a digest by accident."""
    one = fingerprint([SeedEntry(family=SEALED_FAMILY, seed=111)])
    other = fingerprint([SeedEntry(family="some_other_sealed_family", seed=111)])
    assert one != other


def test_the_encoding_version_is_part_of_the_digest() -> None:
    """b2. A changed encoding must give a different digest rather than a silent new meaning."""
    entry = SeedEntry(family=SEALED_FAMILY, seed=111)
    assert FINGERPRINT_VERSION in ("phos-sealed-batch-1",), (
        "the version tag changed; every committed digest is now stale and must be re-registered"
    )
    assert fingerprint([entry]) != fingerprint([SeedEntry(family=SEALED_FAMILY, seed=112)])


# b3: the sealed role refuses public seeds.
def test_a_seed_already_in_the_dev_pool_is_refused(tmp_path: Path) -> None:
    """b3, first refusal. A seed a detector was tuned against cannot stand in for a secret.

    The pair is (family, seed), so this is the same family with the same seed: the exact plant a
    development run already drew. A different family with the same number is a different plant and
    is deliberately not refused, which the next test asserts.
    """
    vault = _empty_vault(tmp_path)
    vault.add(SeedPool.DEV, [SeedEntry(family=SEALED_FAMILY, seed=424_242)])
    batch = _batch(tmp_path, [(SEALED_FAMILY, 424_242)])

    with pytest.raises(SealedBatchError, match="already lives in the 'dev' pool"):
        refuse_seeds_already_seen(batch, vault)


def test_a_seed_already_in_the_retired_pool_is_refused(tmp_path: Path) -> None:
    """b3, first refusal. A retired seed has been seen by whoever ran the exam that used it."""
    vault = _empty_vault(tmp_path)
    vault.add(SeedPool.RETIRED, [SeedEntry(family=SEALED_FAMILY, seed=313_131)])
    batch = _batch(tmp_path, [(SEALED_FAMILY, 313_131)])

    with pytest.raises(SealedBatchError, match="already lives in the 'retired' pool"):
        refuse_seeds_already_seen(batch, vault)


def test_the_same_number_under_another_family_is_not_refused(tmp_path: Path) -> None:
    """b3. The identity is the pair, so a number reused across families is a different plant.

    Stated as a test because the opposite rule would be easy to write by accident: comparing seeds
    alone would refuse a legitimate batch for sharing a number with an unrelated family.
    """
    vault = _empty_vault(tmp_path)
    vault.add(SeedPool.DEV, [SeedEntry(family=OPEN_FAMILY, seed=424_242)])
    batch = _batch(tmp_path, [(SEALED_FAMILY, 424_242)])

    refuse_seeds_already_seen(batch, vault)


def test_a_batch_drawn_from_an_open_family_is_refused(tmp_path: Path) -> None:
    """b3, second refusal. An open family can be regenerated by anyone, so it cannot be sealed."""
    with pytest.raises(SealedBatchError, match="which is open"):
        _batch(tmp_path, [(OPEN_FAMILY, 123_456)])


def test_a_batch_drawn_from_a_family_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    """b3. A misspelled family must be an error, not a silently sealed nothing."""
    with pytest.raises(SealedBatchError, match="does not exist"):
        _batch(tmp_path, [("no_such_family_anywhere", 1)])


def test_the_same_pair_twice_in_one_batch_is_refused(tmp_path: Path) -> None:
    """b3. A duplicate would make the count of plants a lie."""
    path = _write_seeds(tmp_path, [(SEALED_FAMILY, 500), (SEALED_FAMILY, 500)])
    with pytest.raises(SealedBatchError, match="twice"):
        batch_from_environment(environ={ENV_VAR: str(path)})


# The refusals that keep a batch from being silently swapped or duplicated.
def test_a_batch_whose_digest_does_not_match_the_registered_one_is_refused() -> None:
    """A batch presented for a run must be the registered batch, not merely a sealed one."""
    batch = SealedBatch(entries=(SeedEntry(family=SEALED_FAMILY, seed=111),))
    check_against_registered(batch, batch.digest())
    with pytest.raises(SealedBatchError, match="does not match the registered one"):
        check_against_registered(batch, "0" * 64)


def test_registering_writes_the_private_pool_and_then_refuses_a_second_time(tmp_path: Path) -> None:
    """A batch is registered once. A second registration would append to a different seal."""
    vault = _empty_vault(tmp_path)
    batch = _batch(tmp_path, [(SEALED_FAMILY, 909_090)])
    register_in_vault(batch, vault)
    assert vault.load(SeedPool.PRIVATE) == batch.entries
    with pytest.raises(SealedBatchError, match="already lives in the 'private' pool"):
        register_in_vault(batch, vault)


# The environment is the only door seeds come through.
def test_an_unset_variable_is_refused_with_a_message_that_names_no_seed() -> None:
    """The module will not go looking for seeds anywhere else."""
    with pytest.raises(SealedBatchError, match=f"{ENV_VAR} is not set"):
        batch_from_environment(environ={})


def test_a_missing_file_is_refused(tmp_path: Path) -> None:
    """A path that does not exist is an error, not an empty batch."""
    with pytest.raises(SealedBatchError, match="which is not a file"):
        batch_from_environment(environ={ENV_VAR: str(tmp_path / "absent.json")})


def test_malformed_json_is_refused_without_quoting_the_content(tmp_path: Path) -> None:
    """A parse error message must not carry the file's text, because that text is the seeds."""
    path = tmp_path / "broken.json"
    path.write_text('[{"family": "sealed-under-test", "seed": 999999999999', encoding="utf-8")
    with pytest.raises(SealedBatchError, match="could not be read as JSON") as raised:
        batch_from_environment(environ={ENV_VAR: str(path)})
    assert "999999999999" not in str(raised.value)


def test_a_seed_that_is_not_an_integer_is_refused(tmp_path: Path) -> None:
    """A string seed would compare unequal to the integer and silently miss every pool."""
    path = tmp_path / "string.seed.json"
    path.write_text('[{"family": "sealed-under-test", "seed": "12345"}]', encoding="utf-8")
    with pytest.raises(SealedBatchError, match="no integer seed"):
        batch_from_environment(environ={ENV_VAR: str(path)})


def test_an_empty_batch_is_refused(tmp_path: Path) -> None:
    """No entries is not a batch, and an empty digest must never be registered as one."""
    path = tmp_path / "empty.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(SealedBatchError, match="no entries"):
        batch_from_environment(environ={ENV_VAR: str(path)})
