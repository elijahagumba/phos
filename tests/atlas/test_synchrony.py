"""Tests for CrossSubsystemSynchronyModel: subsystem-pair correlation watcher.

Catches attacks where everything moves together — the batch-reactor blind spot
where Mahalanobis scores 0 because no individual signal departs from the joint
model. Synchrony instead watches for physically independent subsystems moving
in lockstep.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy
import pytest

from phos.atlas.synchrony import CrossSubsystemSynchronyModel
from phos.atlas.topology import Subsystem, SubsystemMap
from phos.ontology import Domain, Observation


def _observations(
    n_samples: int,
    subsystem_signals: dict[str, list[str]],
    base_correlation: float = 0.0,
    noise: float = 0.1,
    seed: int = 7,
) -> list[Observation]:
    """Build synthetic observations where named subsystems share a latent driver.

    Each subsystem's signals = base_correlation * shared_driver + independent_noise.
    When base_correlation is high, subsystem pairs move together; when low, they
    are independent.
    """
    rng = numpy.random.default_rng(seed)
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    obs: list[Observation] = []
    shared = rng.standard_normal(n_samples)
    for i in range(n_samples):
        ts = start + timedelta(seconds=30 * i)
        for sub_id, signals in subsystem_signals.items():
            for _sig_idx, feature in enumerate(signals):
                value = base_correlation * shared[i] + rng.standard_normal() * noise
                obs.append(
                    Observation(
                        id=f"obs_{sub_id}_{feature}_{i:06d}",
                        entity_ids=[sub_id],
                        feature=feature,
                        value=float(value),
                        timestamp=ts,
                        domain=Domain.ATLAS,
                    )
                )
    return obs


def test_fits_and_scores_independent_subsystems() -> None:
    """Independent subsystems (correlation ~0) produce no deviations when scored alike."""
    obs = _observations(
        n_samples=400,
        subsystem_signals={
            "reactor": ["reactor.temp", "reactor.level"],
            "jacket": ["jacket.temp", "jacket.flow"],
        },
        base_correlation=0.0,
        noise=0.1,
        seed=7,
    )
    topology = SubsystemMap(
        subsystems=[
            Subsystem(
                subsystem_id="reactor",
                label="Reactor",
                signals=frozenset({"reactor.temp", "reactor.level"}),
                source="test declaration",
            ),
            Subsystem(
                subsystem_id="jacket",
                label="Jacket",
                signals=frozenset({"jacket.temp", "jacket.flow"}),
                source="test declaration",
            ),
        ],
        signal_keys={"reactor.temp", "reactor.level", "jacket.temp", "jacket.flow"},
    )
    model = CrossSubsystemSynchronyModel(
        window_minutes=10, step_minutes=1, min_window_samples=20, subsystem_map=topology
    )
    fitted = model.fit(obs)
    deviations = fitted.score(obs)
    # Same data as training: no deviation expected (correlation matches baseline).
    assert len(deviations) == 0


def test_detects_synchrony_break_in_test_data() -> None:
    """Test data with higher correlation than training produces deviations."""
    train = _observations(
        n_samples=1000,
        subsystem_signals={
            "reactor": ["reactor.temp", "reactor.level"],
            "jacket": ["jacket.temp", "jacket.flow"],
        },
        base_correlation=0.0,
        noise=0.1,
        seed=7,
    )
    test = _observations(
        n_samples=1000,
        subsystem_signals={
            "reactor": ["reactor.temp", "reactor.level"],
            "jacket": ["jacket.temp", "jacket.flow"],
        },
        base_correlation=0.8,  # suddenly coupled
        noise=0.05,
        seed=11,
    )
    topology = SubsystemMap(
        subsystems=[
            Subsystem(
                subsystem_id="reactor",
                label="Reactor",
                signals=frozenset({"reactor.temp", "reactor.level"}),
                source="test declaration",
            ),
            Subsystem(
                subsystem_id="jacket",
                label="Jacket",
                signals=frozenset({"jacket.temp", "jacket.flow"}),
                source="test declaration",
            ),
        ],
        signal_keys={"reactor.temp", "reactor.level", "jacket.temp", "jacket.flow"},
    )
    model = CrossSubsystemSynchronyModel(
        window_minutes=10, step_minutes=1, min_window_samples=20, subsystem_map=topology
    )
    fitted = model.fit(train)
    deviations = fitted.score(test)
    assert len(deviations) > 0
    # All deviations should be for the reactor-jacket pair.
    for d in deviations:
        assert d.expected.feature == "synchrony:reactor:jacket"


def test_derives_subsystems_from_signal_keys_without_map() -> None:
    """Without a declared topology, subsystem ids come from signal key prefixes."""
    obs = _observations(
        n_samples=400,
        subsystem_signals={
            "alpha": ["alpha.sig1", "alpha.sig2"],
            "beta": ["beta.sig1", "beta.sig2"],
        },
        base_correlation=0.0,
        noise=0.1,
        seed=7,
    )
    model = CrossSubsystemSynchronyModel(window_minutes=10, step_minutes=1, min_window_samples=20)
    fitted = model.fit(obs)
    assert ("alpha", "beta") in fitted.subsystem_pairs


def test_refuses_insufficient_data() -> None:
    """Too few samples raises rather than fitting a meaningless baseline."""
    obs = _observations(
        n_samples=3,
        subsystem_signals={"a": ["a.s1"], "b": ["b.s1"]},
        base_correlation=0.0,
        seed=7,
    )
    model = CrossSubsystemSynchronyModel(window_minutes=1, step_minutes=1, min_window_samples=5)
    with pytest.raises(ValueError):
        model.fit(obs)
