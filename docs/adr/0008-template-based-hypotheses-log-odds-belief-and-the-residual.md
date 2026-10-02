# ADR 0008 — Written-down explanations, belief in log-odds, and never knowing for certain

- **Status:** Accepted
- **Date:** 2026-07-31
- **PART:** 4B

## Context

4A ended with `Evidence` that can only exist for a real departure from normal, carrying a calibrated
weight. What it could not do was *explain* anything: PHOS could say "this is unusual, and here is
how sure I am that it is unusual", which is what every anomaly detector says.

4B is the part that has to make good on the architecture's actual claim — competing explanations,
each accumulating evidence for and against, with a confidence that moves as observations arrive.
Three decisions in it are load-bearing enough to record, and each is as much about what PHOS refuses
to claim as about what it computes.

## Decision

**1. Explanations are written down, not inferred, and the code says so.**

A `HypothesisTemplate` is a human-authored label, prior, and two lists of `EvidencePattern` — the
patterns that argue for the explanation and the patterns that argue against it. The engine's entire
generative act is to notice that a piece of evidence matches a pattern and instantiate that
template. Nothing infers, generalises, or discovers a new *kind* of explanation. Constitution §3.6
asks for that honesty in naming, and the names are `HypothesisTemplate`, `TemplateLibrary`,
`instantiate`; the module docstring says outright that this is not open-ended reasoning.

The pattern language is deliberately tiny: `EvidenceKind` and `EntityType`, combined with AND, both
optional. That smallness buys a real guarantee. Because the language is two finite enumerations,
"could these two patterns match the same evidence?" is **decidable**, so `HypothesisTemplate`
refuses at construction time to declare a pattern that both supports and contradicts it. A role is
therefore single-valued by construction rather than by convention — which is what makes a confidence
reconstructable from the stored evidence lists at all. A richer matcher (predicates, callables,
regexes) would buy expressiveness and lose exactly that.

Co-occurrence in time is deliberately *not* in the pattern language, even though the PART lists it
among the things a matcher may test. It is a property of a set of facts rather than of one, so it
lives in the engine, which holds the correlation window. `EvidencePattern.matches` answers about one
piece of evidence; asking it about co-occurrence would mean handing it the rest of the stream.

Template identity is the pair `(domain, template_id)`, not the id alone. The same generic
explanation is registered once per engine, and `Hypothesis` records both fields, so provenance loses
nothing.

**2. Belief updates in log-odds, and confidence can never reach certainty.**

`update_confidence` converts the current confidence to log-odds, adds `EVIDENCE_STRENGTH × weight`
(positive for supporting, negative for contradictory), and converts back through a logistic. Four
properties follow, and all four are requirements the PART states:

- **Bounded by construction.** No clamping of a score that wandered out of range, no squashing
  function invented on top of numbers that were already probabilities.
- **Proportional to trust.** The weight is 4A's calibrated probability, so evidence the calibrator
  half-believes moves belief half as far. This is the reason 4A insisted on calibrating first.
- **Monotone.** Supporting evidence never lowers confidence; contradictory never raises it. Evidence
  of weight 0 moves nothing, which is what a calibrated 0 ought to mean.
- **Order-independent.** Each piece contributes an additive term, and addition commutes. This is not
  a nicety: `Hypothesis` stores supporting and contradictory evidence in *two separate lists* and so
  does not record how they were interleaved. Order-independence is what makes that loss free, and
  what makes `reconstruct_confidence` — replaying the stored lists to rebuild the stored number —
  exact rather than approximate. Constitution §3.2 is a passing test rather than an aspiration.

Certainty is unreachable because odds multiply and never arrive at infinity. Float64 does not respect
that on its own — `1 / (1 + exp(-40))` rounds to exactly `1.0` — so the log-odds are bounded at
±27.6 (`_EPSILON = 1e-12`). Without that bound, roughly thirty-seven fully-trusted observations would
make PHOS report a probability of 1, and "PHOS is certain" is a claim the system is not entitled to
make about anything. The bound costs strict monotonicity in the far tail: past about twenty-five
full-weight pieces of evidence pulling one way, further evidence stops moving the number, and
reconstruction returns the saturated value. That is stated in the docstring rather than hidden.

`EVIDENCE_STRENGTH` is `log(3)`: one fully-trusted piece of evidence makes its hypothesis three
times more likely relative to the alternatives. Modest on purpose — several independent observations
should be needed to move an explanation from unlikely to probable.

**3. "Insufficient evidence" is a hypothesis, not the leftover.**

Every competing set contains a real hypothesis whose template declares no patterns, so no evidence
ever attaches to it and its confidence stays at its prior (0.30). It is created for every domain the
library covers before any evidence arrives, so *before the first observation the only explanation on
the table is that we do not know*. `TemplateLibrary.residual_for` supplies the canonical one when a
domain has not registered its own; PARTs 5–6 may reword it or set a domain-specific prior, and
cannot remove it.

It earns its place twice over. It is what "we do not know" looks like when it is a first-class
answer instead of an empty list — a single weak observation leaves the residual leading, which is
correct. And in `normalise` it holds real mass, so no explanation can ever normalise to 100%: the
percentages a UI shows are a distribution that always includes not-knowing.

**4. The engine reports; it does not decide.**

`competing()` returns every explanation currently on the table, *including the ones the evidence has
argued against*. Pruning marks a hypothesis `PRUNED` below `pruning_threshold` (0.02) and nothing
more: it is not deleted, not hidden, and the mark is recomputed on every update so later evidence
revives it. "Considered, and the evidence argues against it" is information an analyst wants.

The correlation window does two jobs with one number. It decides which facts belong to one story —
same domain, overlapping entities, within the window — and how long a hypothesis keeps accumulating
before a fresh one spawns at its prior. Without the second, a template's confidence would compound
across unrelated hours and report belief in something no operator would call one incident.

A narrative groups evidence by co-occurrence **and** by shared explanation. The second rule is what
makes a story self-contained: every piece of evidence a narrative's confidences were built from is
in that narrative, so the number an operator reads can be rebuilt from the story printed beside it.
`overall_confidence` is the leading hypothesis's own confidence rather than its normalised share,
because the raw number is reconstructable from one evidence list while a normalised share requires
the whole set — traceability decides the tie.

## Consequences

- **PHOS now does the thing it claims to do**, on synthetic telemetry, before either engine exists:
  `test_the_whole_reasoning_loop_runs_on_synthetic_telemetry` drives observations through a Gaussian
  baseline, 4A's out-of-band filter and calibrator, and 4B's engine, then walks the displayed
  confidence back through narrative → evidence → deviation → the observation that fell outside its
  learned range.
- **A hypothesis confidence is not yet a calibrated probability, and must not be surfaced.** This is
  the sharpest limitation of the PART and it is deliberate. Evidence weights are calibrated; the two
  numbers that turn them into a hypothesis confidence — each template's prior and `EVIDENCE_STRENGTH`
  — are unmeasured placeholders. Under Constitution §3.3 that puts hypothesis confidence in the same
  position `uncalibrated_confidence` was in before 4A: honest for ordering competing explanations,
  not yet fit for a user-facing number. It is stated in `phos.reasoning.belief`, in the package
  docstring, and here.
- **Measuring those two numbers needs data PHOS does not have.** BATADAL and HAI label *attack* and
  *normal*; they do not label *explanations*, so no corpus in the registry can tell us the base rate
  of "unauthorised control activity" versus "maintenance", or how strongly one deviation
  discriminates between them. PARTs 5–6 own that for their domains, and it may need labelled
  incident data rather than labelled anomalies.
- **The generic templates are placeholders and are named so.** `generic_anomalous_activity` and
  `generic_benign_change` divide the world crudely — behaviour that keeps failing to match
  expectation versus a change in the environment's structure. Real environments do not divide that
  cleanly. The `generic_` prefix is asserted by a test so the naming cannot quietly drift into
  implying domain knowledge.
- **`ReasoningConfig.seed` is unused, and says so in its own docstring.** Nothing in the engine is
  stochastic. The field exists because Constitution §6 wants one configurable source of randomness,
  and a later stochastic step must take it from there. Recorded because the alternative — an unused
  seed nobody mentions — is exactly the `SplitPolicy(seed=...)` defect still open from PART 3.
- **Narrative assembly is quadratic in the evidence held.** Co-occurrence is tested pairwise. Fine
  for a working set; a long-running engine needs a bounded stream or a spatial index.
- **The engine reads a store but never writes to one.** It resolves entities so templates can
  constrain on entity type. Persisting hypotheses and narratives is the caller's decision, partly
  because a hypothesis is re-emitted under the same id on every update and `EvidenceStore` rejects
  duplicate ids by design.

## Alternatives considered

- **Let the engine write hypotheses to the store as they evolve.** Rejected: every belief update
  produces a new `Hypothesis` value under the same id, and the store refuses duplicate ids precisely
  so that history cannot be silently rewritten. Working memory belongs in the engine; the caller
  persists the result.
- **Recompute confidence from the full evidence lists after each attachment**, instead of applying
  the incremental rule. It would make reconstruction exact even under saturation. Rejected: the PART
  specifies an incremental `update_confidence`, and order-independence already makes the two agree
  everywhere except the far tail, where the honest answer is to document the limit.
- **Normalise inside the engine so stored confidences sum to 1.** Rejected: a hypothesis's
  confidence answers "how well does the evidence support this?", which is a property of that
  hypothesis and its evidence alone and stays reconstructable. Normalising is a presentation
  question — "of the explanations on the table, how does belief divide?" — so `normalise` is a
  separate function whose docstring warns that its output must never be stored back.
- **Drop pruned hypotheses from the competing set.** Rejected outright: it is the collapse this
  engine exists to refuse. Pruning marks, and the mark is reversible.
- **Give the residual a confidence that decays as explanations gain support.** Rejected as
  double-counting: normalisation already shrinks its share as the others earn belief, and a decaying
  prior would make "we do not know" depend on the very numbers it exists to be independent of.
- **A richer pattern language (predicates or callables in templates).** Rejected: it would forfeit
  the decidable-overlap check that makes a role single-valued, and it would let arbitrary code decide
  what evidence means, which is how a template library stops being a curated one.
- **Let evidence carry its own role.** Rejected — it is the design `Evidence` already refuses in
  PART 1, and correctly: a scheduled maintenance window supports "benign change" *and* contradicts
  "unauthorised activity". The role belongs to the link, and `test_one_piece_of_evidence_can_support
  _one_and_contradict_another` pins it.
