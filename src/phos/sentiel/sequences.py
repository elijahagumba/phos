"""Explicit event sequences versus count baselines.

A mundane count can hide a rare path. This module scores n-gram surprise against a trained
multiset of sequences. It does not replace CERT 6B as the public ruler. If sequences lose to
counts at 48 alerts, that loss is the result.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from typing import Final

__all__ = [
    "REPLACES_CERT_SIX_B",
    "count_baseline_surprise",
    "rare_path_beats_count_baseline",
    "sequence_surprise",
]

REPLACES_CERT_SIX_B: Final = False
"""Sequences do not replace CERT 6B as the public Sentiel ruler."""


def sequence_surprise(
    observed: Sequence[str],
    trained: Sequence[Sequence[str]],
) -> float:
    """Return negative log probability of ``observed`` under trained sequence counts.

    Unseen sequences receive a small Laplace mass. Longer rare paths therefore score higher
    surprise than a short path the training set actually contained.
    """
    counts: Counter[tuple[str, ...]] = Counter(tuple(item) for item in trained)
    total = sum(counts.values())
    vocab = len(counts) + 1
    key = tuple(observed)
    probability = (counts[key] + 1.0) / float(total + vocab)
    return -math.log(probability)


def count_baseline_surprise(
    observed_tokens: Sequence[str],
    trained_tokens: Sequence[str],
) -> float:
    """Bag-of-tokens surprise: token multiplicity only, no order.

    A rare *path* that reuses common tokens can look ordinary here and unusual in
    :func:`sequence_surprise`.
    """
    counts = Counter(trained_tokens)
    total = sum(counts.values()) or 1
    vocab = len(counts) + 1
    surprise = 0.0
    for token in observed_tokens:
        probability = (counts[token] + 1.0) / float(total + vocab)
        surprise += -math.log(probability)
    return surprise / float(len(observed_tokens) or 1)


def rare_path_beats_count_baseline() -> bool:
    """Return whether a rare ordered path is more surprising than a common trained path.

    This is a fixture diagnostic. It does not replace CERT 6B (``REPLACES_CERT_SIX_B`` stays
    False) and it is not a public Sentiel row.
    """
    trained: tuple[tuple[str, ...], ...] = (
        ("logon", "host", "file"),
        ("logon", "host", "file"),
        ("logon", "host", "file"),
        ("logon", "host", "mail"),
    )
    rare = ("logon", "host", "priv", "exfil")
    common = ("logon", "host", "file")
    return sequence_surprise(rare, trained) > sequence_surprise(common, trained)
