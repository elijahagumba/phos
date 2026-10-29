# Competing explanations

**What this is:** the subsystem PHOS exists for. Everything before this asks “is this unusual?”
This asks “what could account for it, what argues for and against each story, and how sure can
anyone be yet?”

**Why it exists:** a single red score is not an investigation. Operators need a **set** of live
explanations, with evidence tagged *supporting* or *contradictory*, and a confidence that can
move as facts arrive.

## A detective’s shortlist, not an open-ended genius

PHOS does **not** invent theories in free prose. Candidate explanations come from a **written
template library** — a shortlist a domain expert could read:

- For a plant: sensor fault, maintenance, process upset, unauthorised control, or “we do not know
  yet.”
- For an organisation: benign role change, peer anomaly, compromised account, insider misuse, or
  “we do not know yet.”

The code is named honestly (`HypothesisTemplate`, `TemplateLibrary`). Matching is pattern-based:
kinds of evidence, kinds of entity. A template that would count the same fact as both for and
against is **refused at construction**, like a form that will not let you tick yes and no on one
line.

This is not general intelligence. It is a curated checklist that can be audited.

## “I don’t know” is a first-class answer

**Insufficient evidence** is always on the table. Before any evidence, it is supposed to lead:
nothing starts more likely than “we do not know yet.” That is a product rule, not a slogan. If the
data cannot support a verdict, PHOS should **refuse**, not pick the least-bad poster.

The same rule applies when two stories **share the lead**. Saturated confidences (or two scores
within a tiny declared epsilon) are a **tie**, not a unique winner. Constitution-level
reproducibility still lists the tied ids in a stable order; it does not license naming
`engineering_maintenance` the leader because it sorts before `unauthorised_control_activity`,
or naming Sentiel's `benign_role_change` because it sorts before `compromised_account`. Atlas
and Sentiel stories both use the same ranker. The competing set **raises insufficient evidence**
to the front. The rivals stay visible underneath. That is
[ADR 0036](../docs/adr/0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md) and
[ADR 0045](../docs/adr/0045-sentiel-ranking-shares-0036-narrative-confidence-unset.md).

## Belief moves in small, reversible steps

Each piece of evidence nudges belief in log-odds (a fairer scale than adding raw percentages).
Supporting evidence pushes one way; contradictory evidence pushes the other. The size of the nudge
is limited by how much we trust that evidence.

Certainty is unreachable on purpose. After enough “fully trusted” observations a naive computer
would round to 100%. PHOS caps that so it can never report a probability of exactly 1 about the
world.

The update is **order-independent**: seeing fact A then B yields the same confidence as B then A.
That is what makes a displayed number reconstructable from the stored lists.

## The evidence boundary — not every blip is a clue

A model may emit many “candidates” so the harness can sweep thresholds. **Evidence** is stricter:
the reading must sit **outside** the learned expected range. A large score that is still inside the
band does not become a clue. Analogy: a slightly warm oven is not a fire.

Later, **relationship changes** (who commands whom) get a second door into evidence, because they
have no numeric “expected range” to step outside of. A finding still has to **belong** to the
window’s story: sharing a clock is not enough
([who belongs in the story](15-silence-stretch-and-who-belongs-in-the-story.md)).

## What this is not

- Hypothesis **confidences** from the reasoning engine are **not** calibrated user-facing
  probabilities. They order explanations. They must not be shown as “82% sure this is an insider.”
  A story’s `overall_confidence` is left unset until that calibration exists
  ([ADR 0045](../docs/adr/0045-sentiel-ranking-shares-0036-narrative-confidence-unset.md)).
- On plant telemetry alone, “attacker turned a valve” and “operator ran a legitimate change” can
  look identical. An **untyped** new command relationship still supports both. A **marked unknown
  master** does not: that finding contradicts maintenance. Known-link changes stay indistinguishable
  ([listening to commands](07-atlas-listening-to-commands.md)).
- Atlas and Sentiel stories do not yet share one incident. That stitching is Intelligence, unbuilt.

## Where to read more

- Code: `src/phos/reasoning/`
- Decisions: [ADR 0007](../docs/adr/0007-the-evidence-boundary-and-a-calibrated-confidence.md),
  [ADR 0008](../docs/adr/0008-template-based-hypotheses-log-odds-belief-and-the-residual.md),
  [ADR 0027](../docs/adr/0027-unknown-master-writes-are-not-maintenance.md),
  [ADR 0036](../docs/adr/0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md),
  [ADR 0038](../docs/adr/0038-a-windows-story-attaches-graph-findings-by-entity-reachability.md),
  [ADR 0045](../docs/adr/0045-sentiel-ranking-shares-0036-narrative-confidence-unset.md)
