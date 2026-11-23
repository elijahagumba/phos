"""The referee refuses to fit a corpus the data-tier rule forbids.

ADR 0461. The safe answer matches ``phos.genesis.tiercheck``: when a corpus is
never-read, or barred by licence, the call stops before any path is opened.
It does not warn and continue.
"""

from __future__ import annotations

from typing import Final

#: The record that quarantined the factories and the three builders.
QUARANTINE_ADR: Final = "0461"


class QuarantinedCorpusError(RuntimeError):
    """Raised when a referee entry point would fit or score a forbidden corpus.

    The call raises before it opens a path, reads a file, or fits a model.

    Attributes:
        corpus: The corpus name the caller asked for.
    """

    def __init__(self, corpus: str) -> None:
        """Record ``corpus`` and cite the quarantine record.

        Args:
            corpus: The corpus the entry point would have fitted or scored.
        """
        self.corpus = corpus
        super().__init__(
            f"{corpus} is quarantined by ADR {QUARANTINE_ADR}. "
            "The referee does not fit or score it, and this call returns "
            "before any file is opened."
        )
