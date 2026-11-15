"""The JSON skeletons ``scripts/genesis.py template`` prints.

Filling a skeleton and handing it to the matching subcommand is the whole interface, which is why
the keys are the charter's own requirements rather than a loose dictionary. A field that exists
here is a field the record will refuse to go without: ``why_it_might_be_wrong`` is section II step
5, ``falsifier`` is step 6, ``baseline`` is step 7, and ``failures`` is section IV's requirement
that unexpected results are recorded rather than dropped.
"""

from __future__ import annotations

from typing import Any, Final

#: Section XII's nine criteria, each at the neutral 3 so that a filled-in score is a judgement
#: somebody made rather than a default that drifted through.
_NEUTRAL_PRIORITY: Final[dict[str, int]] = {
    "significance": 3,
    "originality": 3,
    "feasibility": 3,
    "information_gain": 3,
    "tractability": 3,
    "relevance": 3,
    "operational_impact": 3,
    "evidence": 3,
    "cost": 3,
}

TEMPLATES: Final[dict[str, dict[str, Any]]] = {
    "question": {
        "title": "",
        "frontier": "V.1 latent industrial process representations",
        "opened": "YYYY-MM-DD",
        "state_of_the_art": "",
        "gap": "",
        "priority": dict(_NEUTRAL_PRIORITY),
        "refs": [],
    },
    "experiment": {
        "question": "Q-0001",
        "declared": {
            "date": "YYYY-MM-DD",
            "hypothesis": "",
            "why_it_might_be_wrong": "",
            "falsifier": "",
            "baseline": "",
            "command": "",
            "corpus": "",
            "tier": "iterate",
            "result_name": "",
            "challenger_sha256": None,
            "bars": [{"id": "b1", "metric": "", "comparator": ">=", "threshold": 0.0, "text": ""}],
        },
    },
    "measurement": {
        "date": "YYYY-MM-DD",
        "commit": "",
        "report": "",
        "values": {"b1": 0.0},
        "failures": "",
        "notes": "",
    },
    "finding": {
        "claim": "",
        "evidence": [],
        "prior_work": [],
        "improvement": "",
        "corpora": [],
        "limitations": "",
    },
}
