# ADR 0023 — Per-entity reasoning, the completed competing set, and what CERT r4.2 can unblock

- **Status:** Accepted
- **Date:** 2026-08-21
- **PART:** 6C
- **Supersedes:** nothing
- **Depends on:** [ADR 0008](0008-template-based-hypotheses-log-odds-belief-and-the-residual.md),
  [ADR 0014](0014-command-evidence-the-second-boundary-door-and-the-unrun-measurement.md),
  [ADR 0020](0020-enterprise-data-intake-entity-scoped-truth-and-what-cert-actually-ships.md),
  [ADR 0022](0022-peer-group-baselining-and-the-scoring-shape-that-survives-a-wide-feature-set.md)

## Context

PART 6C wires the enterprise explanations onto PART 6B's scorer: an entity-window's per-feature
contributions become evidence through 4A's boundary, group into at most one behaviour event per
family, and reach 4B's `ReasoningEngine` with the enterprise template library. That wiring was
written and left red — nine failing tests, and the six substantive ones all said the same thing in
different words. The residual did not lead on thin evidence; explanations that were considered and
unsupported were missing from stories entirely; and a hypothesis about one person cited evidence
about another.

The six were one defect. `ReasoningEngine` identifies the hypothesis a piece of evidence should join
by `(domain, template_id)` and nothing else:

```python
_TemplateKey = tuple[Domain, str]
"""How a hypothesis is identified while it accumulates: its domain and its template."""
```

That is exactly right for Atlas, whose evidence is all about one plant, and where merging a window's
events into one story is the answer rather than a bug. It is wrong for an organisation. Sentiel's
evidence is about a thousand different people, so one pass over the corpus accumulates every
colleague's access departure into a *single* `compromised_account` hypothesis — and then
`ReasoningEngine.narratives`, which treats "the same hypothesis rests on both" as evidence that two
facts belong to one incident, merges their stories. In the fixture corpus, `NORMAL01`'s one faint
departure and `INSIDER1`'s five loud ones landed in one narrative led by `compromised_account`. Two
invariants fell at once: a confidence an operator read for one person had been built partly from
another person's behaviour (Constitution §3.2, traceability), and the honest "we do not know" was
displaced on thin evidence by the cheapest malicious explanation on offer (§3.3).

The second symptom has a separate cause with the same root. A template spawns a hypothesis only when
evidence matches it, so `ReasoningEngine.competing` — and therefore a narrative's hypothesis list —
holds the residual plus the templates that matched, and nothing else. A story assembled that way
silently drops the explanations that were weighed and found unsupported, which is precisely the
collapse to a verdict this system exists to refuse.

## Decision 1 — Reasoning runs **once per entity**

`SentielEngine._reason` partitions the behaviour events by entity and constructs one
`ReasoningEngine` per person, rather than one for the corpus.

**Why this is the correct unit and not a workaround.** A hypothesis is a claim *about somebody*.
"This account is being used by someone other than its owner" is not a proposition about an
organisation, and a confidence in it that rises because an unrelated colleague also worked late is
not a weaker measurement of the right thing — it is a measurement of nothing. Atlas's single pass and
Sentiel's per-entity passes are the same rule applied to two domains: reason over the scope the
explanation is about. Atlas's scope happens to be the whole corpus because the corpus is one plant.

**Why it costs nothing else.** The belief update is additive in log-odds and order-independent, so
partitioning changes no arithmetic for any single person; it only stops arithmetic being shared
between people who have nothing to do with each other. Determinism is preserved by iterating
entities in sorted order and ordering the resulting narratives by their earliest evidence and then by
entity, so the output is a function of the evidence rather than of dictionary iteration.

**What it costs.** One `ReasoningEngine` per entity means one residual hypothesis per entity, which
is correct — every person's story needs its own "we do not know" — but it does mean the store holds
hypotheses proportional to the population rather than to the template count. On r3.1's 1,000 users
that is thousands of small immutable objects, which is fine, and it is the same order as the
narratives themselves. A corpus-scale runner should stream by entity rather than hold all of them.

**Rejected: teach `ReasoningEngine` to key on entity.** It is the better long-term fix and it is not
available to this PART. 6C's contract is to consume the spine unmodified — a test asserts
`src/phos/reasoning` is byte-identical to the 6B commit — and changing the hypothesis key would
change Atlas's behaviour too, which 6C may not do without measuring Atlas again. The seam is
recorded here for the PART that is free to touch both: promote the entity dimension into
`_TemplateKey`, then delete `SentielEngine._reason`'s partitioning.

## Decision 2 — Every story reports every registered explanation, including the untouched ones

`SentielEngine._completed` adds, to each narrative, a fresh `HypothesisTemplate.instantiate()` for
every template in the domain's library that no evidence in that story touched, and re-ranks the whole
set by confidence.

An untouched hypothesis sits at its prior, holds no evidence, and cites nothing. That is not a
weakness in the report; it is the report. "This explanation was on the table, the evidence bore on it
nowhere, and here is the base rate it therefore still carries" is what distinguishes a competing set
from a verdict, and it is what makes the leading explanation's margin readable — `benign_role_change`
at its 0.155 prior beside `compromised_account` at 0.937 says something that omitting the first does
not.

The ranking is the reasoning engine's own — confidence descending, then template id, then assembly
order — restated in `_ranked` rather than reached for, because `ReasoningEngine._ranked` is private
and 6C may not widen it. The duplication is two lines and is noted here so a later PART can promote
it once, alongside Decision 1's seam.

**Why the templates are not given contradictory patterns instead.** Making every family match every
template would put all four explanations in every story without any new code. It would also be
false: `phos.sentiel.templates` records that a departure in access or data handling is deliberately
*not* contradictory evidence against a sanctioned role change, because a real role change produces
both. Manufacturing a contradiction to fix a reporting gap would corrupt the belief arithmetic to
tidy up a list.

## Decision 3 — CERT r4.2 does **not** unblock the peer-relative claim, and its shape is not what it is usually described as

`scripts/probe_cert_release.py` is a read-only probe over the small `answers` archive, which ships
separately from the multi-gigabyte events. Run against r4.2 it establishes:

| | |
| --- | --- |
| Labelled incidents | **70** |
| Scenarios | **3**, not 5 |
| Scenario 1 | 30 insiders — self-relative |
| Scenario 2 | 30 insiders — self-relative |
| Scenario 3 | 10 insiders — account holder is not the actor |
| Peer-relative positives | **0** |

CERT ships five scenario descriptions and r4.2 contains the first three of them. Any plan budgeting
for five scenarios' worth of positives in r4.2 was budgeting for r5.2, which holds 99.

**The peer claim stays retired-in-place.** `peer_anomaly` needs a labelled insider who is
unremarkable against their own past and remarkable against their team's. Reading CERT's own
`answers/scenarios.txt`, scenario 1 is "a user who *did not previously* use removable drives or work
after hours" and scenario 2 acts "at markedly higher rates than *their previous activity*" — both
self-relative, which is what ADR 0022 found for r3.1 and what the probe now confirms for r4.2's 60
insiders. Scenario 5, the only description framed around a group ("a member of a group decimated by
layoffs"), frames the *motive*; what is observable is still one person uploading documents they did
not previously upload. `PEER_REGISTER_UNTESTED_CAVEAT` therefore stands, and downloading r4.2 would
not have removed it.

**What r4.2 does unblock is the competing-hypothesis benchmark.** Scenario 3's 10 insiders are the
first labelled case in any release PHOS reads where *an account is driven by somebody other than its
owner* — a sysadmin who "uses the collected keylogs to log in as his supervisor". That is the
situation `compromised_account` claims to explain, and discriminating it from `insider_misuse` is the
one thing 6C's template set asserts and no corpus has yet tested. 10 positives is a coarse
denominator and must be reported as one.

The register readings are a judgement about prose, so each carries the verbatim quote it rests on and
a test asserts every quote is still present in CERT's own file. A judgement whose supporting quote
has drifted from its source is worse than no judgement.

## Decision 4 — The probe reads headers, and reports "unchecked" rather than "compatible"

`phos.sentiel.cert`'s `LogSpec` set was written against real Release 3.1 headers, read off the files
rather than off the published schema, and ADR 0020 D5 records why: CERT's published schemas do not
match its shipped files. So the specs cannot be assumed to hold for another release, and the probe
applies the reader's own two rules — a missing required column, and a column the spec cannot account
for — non-fatally, one line per log.

When a release's events are absent the probe prints the specs that *would* have to hold and says that
nothing was checked. The distinction between "unchecked" and "compatible" is the only thing that
makes the instrument worth having, and a test asserts the words. Verified against r3.1, whose events
are on disk: all five logs report readable, agreeing with the reader that reads r3.1 in production.

The header read is bounded to one line rather than one CSV record. A header carries no quoted
commas, so the two are the same thing here, and r3.1's `http.csv` is 12 GB — a probe should not be
able to walk it.

## Consequences

**What is now true.** 2,655 tests pass, `mypy --strict` is clean across all 205 source files for the
first time since PART 6·D, and `ruff` is clean. Coverage on the code this PART added: `engine.py`
96%, `templates.py` 97%, `probe_cert_release.py` 98%.

**What this PART still refuses to claim.** 6C changed *explanation*, not detection ranking, and it
has no corpus-scale runner — `SentielEngine` is exercised on a real CERT slice by its tests and
nowhere else. **It therefore publishes no detection number, and PART 6B's stand unsuperseded.** The
hypothesis confidences remain uncalibrated and unsurfaceable under Constitution §3.3, for the four
reasons `UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT` gives; the third of them — that the belief update
treats consecutive daily windows of one persistent behaviour as independent — is *sharpened* by
Decision 1 rather than fixed by it, because a single person's five days of departure now accumulate
into that person's own hypothesis with nothing else diluting it.

**Deferred, and named rather than left to be discovered.** No corpus-scale Sentiel runner exists;
the `_operating_point` degenerate-sweep defect at `src/phos/sentiel/evaluation.py:311` is still open
from 6B; narrative assembly is still quadratic in the evidence held, now per entity, which is
strictly better but still quadratic. The two shared-spine seams Decisions 1 and 2 record — the
entity dimension in `_TemplateKey`, and the duplicated ranking — belong to the first PART free to
modify `phos.reasoning` and Atlas together.
