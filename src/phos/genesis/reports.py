"""The session research report, assembled from the record rather than written by hand.

Charter section XIII asks every session to end with a report naming the experiments conducted,
the quantitative results, the failed experiments and the next priorities. Written by hand that
report is a summary, and a summary is the one artefact that can disagree with the evidence
without anything noticing. Here it is a projection of the records, so it cannot claim an
experiment that is not in the store or hide one that is.

What it deliberately does not contain is a conclusion. The renderer states what was measured and
against which declared bar; whether that amounts to a contribution is the judgement a human and
an independent review make, and it goes in the finding, not here.
"""

from __future__ import annotations

from phos.genesis.levels import ladder_report
from phos.genesis.render import finding_summary
from phos.genesis.store import Snapshot


def session_report(snapshot: Snapshot, since: str) -> list[str]:
    """Return the report lines for every record dated ``since`` or later.

    Args:
        snapshot: Everything the store holds. A snapshot rather than the store itself, so the
            caller has already seen which files would not load and can say so.
        since: An ISO date. Records older than this are left out of the per-experiment
            sections; the discovery ladder is always reported in full, because a claim that
            already holds a level is part of the state a session must not contradict.

    Returns:
        One string per line, no trailing newlines.
    """
    experiments, findings = snapshot.experiments, snapshot.findings
    judged = [
        e
        for e in experiments.values()
        if e.measured is not None and e.measured.date.isoformat() >= since
    ]
    kept = [e for e in judged if e.verdict is not None and e.verdict.outcome == "kept"]
    refused = [e for e in judged if e.verdict is not None and e.verdict.outcome == "refused"]
    declared = [
        e
        for e in experiments.values()
        if e.phase == "declared" and e.declared.date.isoformat() >= since
    ]

    lines = [
        f"# GENESIS research report — records dated {since} or later",
        "",
        f"## Experiments judged ({len(judged)}: {len(kept)} kept, {len(refused)} refused)",
        "",
    ]
    for experiment in sorted(judged, key=lambda e: e.id):
        verdict, measured = experiment.verdict, experiment.measured
        assert verdict is not None and measured is not None
        lines.append(f"- **{experiment.id}** {verdict.outcome} — {experiment.declared.hypothesis}")
        for bar in experiment.declared.bars:
            value = measured.values[bar.id]
            mark = "met" if verdict.per_bar[bar.id] else "missed"
            lines.append(f"  - {bar.metric} {bar.comparator} {bar.threshold:g}: {value:g} {mark}")
        lines.append(f"  - failures: {measured.failures}")

    if refused:
        lines += ["", "## Failed experiments, kept on the record", ""]
        lines += [f"- {e.id}: {e.declared.hypothesis}" for e in sorted(refused, key=lambda e: e.id)]

    lines += ["", f"## Declared and not yet run ({len(declared)})", ""]
    lines += [f"- {e.id}: `{e.declared.command}`" for e in sorted(declared, key=lambda e: e.id)]

    lines += ["", "## Discovery ladder", ""]
    lines += [
        f"- {name}: {count}" for name, count in ladder_report(list(findings.values())).items()
    ]
    if findings:
        lines += ["", "## Claims on the record", ""]
        lines += [
            f"- {finding_summary(f)}"
            for f in sorted(findings.values(), key=lambda f: (-f.level, f.id))
        ]
    return lines
