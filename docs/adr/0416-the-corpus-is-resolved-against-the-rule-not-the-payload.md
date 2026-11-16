# ADR 0416 — The corpus is resolved against the rule file, so a never-read dataset cannot be declared

- **Status:** Accepted
- **Date:** 2026-11-03
- **PART:** Method. Phase C of `docs/genesis-architecture-proposal.md`
- **Supersedes:** nothing. [ADR 0412](0412-research-and-engineering-run-through-a-record-a-machine-can-read.md)
  stands; this makes one of its sentences true. [ADR 0415](0415-the-record-store-survives-two-writers-and-its-own-damage.md)
  named this as what it did not fix
- **Depends on:** [ADR 0412](0412-research-and-engineering-run-through-a-record-a-machine-can-read.md),
  [ADR 0413](0413-cursor-has-skills-and-hooks-and-the-gate-is-wired-into-both.md),
  [ADR 0414](0414-the-five-guards-are-functions-and-both-editors-run-them.md),
  [ADR 0117](0117-two-loops-a-seen-ledger-and-the-held-out-bank.md),
  [ADR 0143](0143-the-plant-map-fails-the-gate.md), [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md)

## Context

ADR 0412 stated, in its own text and in the charter and the always-apply rule repeated from it:

> A `never`-tier corpus stays unread — the record refuses to declare one.

**It did not.** The architecture audit declared a run on `hai-21.03` — named in
`docs/rules/data-tiers.md` under "**Never read, score or iterate on**" — and GENESIS accepted it,
because the payload carried `"tier": "iterate"`. `Declaration._never_tier_is_not_declarable` refused
the *string* `never`. Nothing compared the `corpus` field against the rule file, so the `tier` field
was an author's assertion and the model was checking the assertion against itself.

This is the same failure mode the project keeps finding: a check that exists in prose, is believed
to be enforced in code, and is enforced nowhere. It is the reason the proposal's §0.2 comes before
any new capability, and the reason ADR 0415 ended by naming this as still open.

The older `red_tier` guard did warn on an actual read, so the hole is a declaration that would have
been caught later by a warning rather than never. It is still a declaration the record accepted, and
ADR 0412 claims it cannot.

## Decision

**1. The tier is resolved from the rule file, not read from the payload.** `resolve` in
`src/phos/genesis/tiercheck.py` takes a corpus name and asks `docs/rules/data-tiers.md` what it is.
The parser is `phos.guards.tiers` — the one ADR 0414 moved out of the hooks — so there is **one
reading of the rule** in the repository and not a second. `Tiers` gains `sentences`, which records
the rule's own bullet per name so a refusal can quote the text that refused rather than paraphrase
it, and `tier_of`, which resolves one exact name.

**2. `declare` refuses a corpus the rule names never-read, however the tier is filled in.**
The refusal happens before the id is allocated and before the lock is taken, so a refused
declaration spends no number and writes no file:

```
refused: hai-21.03 cannot be declared.
  docs/rules/data-tiers.md — Never read, score or iterate on `hai`, `hai-21.03`, `hai-22.04`, `hai-23.05`, `batadal`.
  the rule names 'hai-21.03' in the never-read tier; the declaration's own `tier` field cannot overrule it, and said 'iterate'
  a run on it cannot be declared; ADR 0117's gate look 1 is spent (ADR 0143) and a new look needs Elijah to authorise it
```

**3. `declare` refuses a corpus it cannot find in the rule file or in `data/registry.json`.**
An unknown corpus is a refusal, not a default. The message names both places that were consulted, and
the count the registry was read at, so "not found" is distinguishable from "the registry could not be
read".

**4. `gate` refuses when the resolved tier and the declared tier disagree.** This is deliberately
*not* `declare`'s job. A declaration naming the wrong tier is still a declaration — it is a record of
what someone intended — and the place a wrong tier must not survive is the moment the run is
authorised. So `declare` writes it and warns on stderr that the gate will refuse it; `gate` refuses
it. The new `GateDecision` verdict is `tier`, and it is **never softenable**: `softenable` remains
true for `silent` alone, so neither editor may turn it into a warning or a question.

**5. The check lives where both editors inherit it.** The decision is in
`phos.genesis.gatehost.decide`, which `scripts/genesis.py gate`, `.claude/hooks/genesis_gate.py` and
`.cursor/hooks/genesis_gate.py` all call. No logic was added to either editor's shim, so ADR 0413's
"the decision moves out of the hooks" is not reopened.

**6. The rule's own catch-all is honoured rather than invented.** `data-tiers.md` says a run may be
made on "any newly registered unseen corpus" after a committed declaration — that is the
`score once` bullet. A corpus the rule does not name but the registry does therefore resolves to
`once`, quoting that sentence, found by searching the parsed rule for it rather than restating it.
Nothing infers a tier from a registry `role` field: that would be the registry overruling the rule,
and a test pins it.

### What the table-driven test is, and why its absence was the phase

`tests/genesis/test_tiercheck.py::TestTheRuleRefusesItsOwnNames` reads `docs/rules/data-tiers.md`
from the repository, parses it, and parametrises over **every name the rule puts in the never-read
tier** — **seventeen** at this commit: the five validation corpora (`hai`, `hai-21.03`, `hai-22.04`,
`hai-23.05`, `batadal`), the five used seed sets (`ARENA_LIAR_SEEDS`, `RED_TEAM_SEEDS`,
`CONFIRM_SEEDS`, `CONFIRM_SEEDS_2`, `CONFIRM_SEEDS_3`), the module the seed sets live in
(`phos.breaking.liar_arena`), the four scripts and the brief named in the same bullet's exceptions,
and `--compare`, which is a flag the parser reads as a token and not a corpus. Each is asserted
refused at declaration, and each is asserted refused again for every value the `tier` field can
legally carry. The table is read from the rule, so a corpus added to that sentence is covered the
moment the sentence lands and nobody edits a test.

Seventeen is more than the five corpora a human would list, and that is the point rather than an
overcount: the parser's reading of that bullet is what the guard has always used, the table tests the
same reading, and `--compare` being in it is the pre-existing artefact ADR 0414 disclosed. Narrowing
what counts as a name is a change to a guard's behaviour and needs its own record — the same sentence
ADR 0414 wrote.

Two tests exist only to stop that table passing vacuously: one asserts the parsed sets are non-empty
in both directions, and one asserts no name sits in two tiers.

### A check that could not fire, and what replaced it

The model's own `_never_tier_is_not_declarable` already refuses `tier: "never"`. That means the
combination *never-tier corpus + `"tier": "never"`* cannot reach `gate` at all: Pydantic rejects the
record before it is written. A gate test for that pair would pass forever while proving nothing.

That is why the gate tests parametrise over the **reachable** tiers only — `iterate` and `once` — and
say so in a comment, and why `test_a_never_read_corpus_is_refused_whatever_tier_the_record_can_carry`
asserts the reachable list is exactly those two. The model's validator is kept, because it gives a
better error at the point of writing; it is simply not counted as the check that closes the hole.

### The one place this differs from the guard beside it

`guards.tiers.check` is **advisory**, so a missing rule file silences it: a guard must not block
every tool call the day a file is renamed. `resolve` is a **declaration**, so a missing rule file
refuses everything: a corpus nobody can classify has not been classified as safe. The two directions
are opposite on purpose, each is the safe direction for its own caller, and both are tested.

## Consequences

**Gained.** ADR 0412's sentence is now true. The audit's exact payload — `hai-21.03` labelled
`iterate` — is refused with exit 3 on the real repository. A corpus the repository has never heard of
is refused rather than silently treated as safe. A wrong tier in a hand-edited or pre-existing record
is caught at the gate, in both editors, from one function. The rule file is the single source: no
corpus name is hard-coded in `src/`, so a name added to the rule is enforced without a code change.

**Cost.** Two file reads per declaration and per gate decision (the rule, and the registry when the
rule does not name the corpus). Both are small and neither is on a hot path. `data/registry.json` is
210 KB, so a gate decision that misses in the rule reads it; that is acceptable at one decision per
shell command but would not be at a thousand.

**Coverage.** The three modules this record touches measure **100%** of statements and branches —
`tiercheck.py` 85 statements and 24 branches, `guards/tiers.py` 71 and 26, `gatehost.py` 65 and 22.
Reaching that on `gatehost.py` needed one test written for it: the pre-existing path that aggregates
several matching declarations was never exercised, and the `tier` verdict is now one of the reasons
that can reach it.

**A narrower reading than ADR 0414's `red_tier`.** This resolves one exact corpus name, not a
substring of a path, because a declaration names one corpus. So it does *not* inherit the
longest-match rule, and it does not inherit ADR 0414's disclosed `--compare` false positive either:
`--compare` is a flag, not a corpus, and appears in `red` only because the parser reads every
backticked token in the bullet as a name. Resolving a corpus exactly sidesteps both. That false
positive is still there in `reasons_for` and is still not fixed here.

**Not claimed.** That any tier resolution ran inside a live Cursor session; the parity tests drive
both real hook scripts as subprocesses with each editor's documented payload, which verifies the
contract and not the integration. No corpus was opened, scored or listed; `eval_runs/log.jsonl` was
not appended; no number was produced and no finding exists at any level; v1 unmoved; P1 is still a
blocked human conversation. Phases E, F and G are untouched, and this record does not start them.
