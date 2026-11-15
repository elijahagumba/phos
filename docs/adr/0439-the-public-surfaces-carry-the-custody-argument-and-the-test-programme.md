# ADR 0439 — The public surfaces carry the custody argument and the test programme

- **Status:** Accepted
- **Date:** 2026-11-15
- **PART:** public record
- **Supersedes:** nothing
- **Depends on:** [0438](0438-the-generator-reproduces-itself-and-the-batch-describes-itself.md), [0433](0433-physics-constrained-plant-randomisation-for-training-data.md), [0381](0381-the-front-door-is-corrected-and-the-freeze-opens-for-figures.md), [0200](0200-the-public-repository-takes-the-house-style.md), [0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md), [0143](0143-the-plant-map-fails-the-gate.md)

## Context

Two things were asked for. The public surfaces should read like the company PHOS is destined to be
rather than like a disclaimer with a repository attached; and they should say how Atlas is proposed
to be tested, with Sentiel's equivalent named.

Both were overdue for the same reason. `docs/voice.md` already governs the register and already
records what is taken from Anthropic and from Palantir, each with what is deliberately not taken.
What it did not have was the word Elijah actually used — **sovereign** — or a ruling on the third
company he named. And the front page described what Atlas does and what it cannot do, and said
nothing about the generator that PARTS R1–R5 built, which is the only answer this project has to
"how would you ever know?"

The second gap was the more serious one. Published figures come from three editions of HAI and from
three hand-written plants: six structures. A detector fitted on all of it has structurally seen six
plants and can do well on them by learning those six. ADR 0433 states this as the diagnosis. The
public page did not state it at all, so a reader who worked it out found it themselves, which is the
worst way for a project with this project's argument to be read.

## Decision 1 — From Theranos, the restraint and not the tense

Elijah named Theranos beside Anthropic as a register worth borrowing. The instinct is right and the
reason it is dangerous is specific, so `docs/voice.md` §9 records both rather than declining the
question.

What made that register work was **word order**: the gravity came before the evidence, and the
claims were in the present tense while the measurement was still owed. By tone alone it is
indistinguishable from PHOS's register — grave, spare, unhurried, beautifully set, plainly not
startup voice — and the *only* thing that separates them on a page is whether the falsifier is
printed beside the claim.

So the take is the restraint, the refusal to look like a startup, and the sense of a document filed
rather than posted. The refusal is the present tense about work not yet done. The operative test,
which any draft can be checked against: **a sentence in the present tense must be checkable today.**
Everything else goes in the future tense and names the thing that would settle it.

This is not a moral note about another company. It is a drafting rule, and it exists because the
failure mode is a register this project is deliberately adopting.

## Decision 2 — "Sovereign" means custody, and it is not a grade

`docs/voice.md` §10 defines the word for PHOS's surfaces, because an undefined superlative is
exactly the borrowed scale §3 forbids. It is earned by **custody**, not by reach, and each clause is
checkable in the repository:

1. The plant writes its own laws — no role from a tag name, no station from a function code, no
   membership from the data (ADR 0123, ADR 0010).
2. Nothing leaves the site. `phos onboard` reads the one local file it is given, makes no network
   call, starts no subprocess, writes only the brief; Atlas does not connect to a control network.
   Both are asserted by tests that read the source (`tests/eval/test_offline_core.py`,
   `tests/atlas/test_onboarding.py`) — **and those are source-shape checks, not a security audit**,
   which is what their own docstrings say and what the voice file repeats.
3. The authority on what happened is the plant's record, not PHOS's model. Where the record cannot
   settle it, Atlas stops. The refusal is the sovereign act.
4. Nobody has to trust PHOS to check PHOS: every published figure reproduces.

**It is explicitly not a tier, a grade, a measurement or a procurement category.**
`docs/refusal-register.md` R27 and ADR 0422 leave *sovereign grade* deliberately undefined; this
record does not define it and nothing written in its name may be quoted as one. Not sayable on any
surface: sovereign-grade anything, "national", critical national infrastructure as something PHOS
serves, or a sovereignty claim about a plant PHOS has not run on, which is every plant.

## Decision 3 — The front page states custody first and the limit in the same breath

The opening paragraph previously led with "There is no company, no product and no customer, yet."
That is true and it is the wrong first sentence: it spends the reader's attention on an absence
before they know what the presence is.

It now leads with what is true today — the plant's laws are the plant's, Atlas hands the register
back checked, nothing leaves the site, it holds nothing and has no opinion the plant's record cannot
support — and the limits follow **in the adjacent paragraph, above the fold**: one researcher with
AI coding agents, no company, no product, no customer, and Atlas has never run on a live plant.
Decision 1's test is satisfied: every present-tense clause in the first paragraph is checkable in
this repository today.

Nothing was removed. The law paragraph is untouched (`docs/voice.md` §11), and no figure, caveat or
"what Atlas cannot do" bullet was weakened.

## Decision 4 — The page says how Atlas is proposed to be tested, and says what has not been scored

A new section, **"How Atlas will be tested"**, placed immediately after "What Atlas cannot do",
because that is where a reader's next question is. It states the defect first (six structures;
held-out seeds hold out noise, not a plant), rejects signal perturbation as the instructive wrong
answer, and then gives the four properties of a drawn plant: a bad draw refused rather than clipped
with 52 of 150 refused, events on four layers with the layer named, the two facts measured rather
than declared, and byte-identical reproduction across fresh processes **together with its converse**.

Three things in it are load-bearing and were nearly left out.

**The sealed family is described honestly.** It is kept out of the registry, the listing and the
published bounds table and loads only behind a switch, so nothing in the generator or its documents
can point a detector-builder at it. **Its source is in the repository and the page says so.**
`src/*` is a wholesale export include, and claiming a public reader cannot reach it would have been
a claim the export contradicts. Sealing is a discipline about what the generator exposes, not a
secret, and that is the sentence on the page.

**"Nothing has been scored on a generated plant" is in the section, not a footnote.** The referee is
not built. No recall, no false-alarm rate and no verdict exists for Atlas on a drawn plant, and the
section forbids quoting one from it.

**The caveat does not soften with volume.** A family generates models; unlimited draws are unlimited
models (ADR 0143). A number measured this way is a diagnosis about how Atlas handles our model of a
plant, never a result about a real one.

## Decision 5 — Sentiel's equivalent is named as unbuilt rather than implied

The page now says that Sentiel's scarcity is worse: one public insider-threat corpus, two insiders,
one found, every number from one estate. The intended answer is the same shape — draw a population
of estates, varying team structures, working rhythms, role changes, joiners and leavers — and
**none of it is built and none of it is declared.** Writing that down is the whole of it. The reason
to publish an unbuilt plan is that the second engine's evaluation problem is already true, and a
reader who finds it unaided finds it as something that was hidden.

## Decision 6 — Two of the generator's documents join the export; the third does not

`docs/sim/README.md` and `docs/sim/coverage.md` are added to `public/manifest.toml`, because the new
section links to both and a dead link on the one part of the page that is about method is worse than
no link. `docs/sim/recon.md` is deliberately **not** added: it is the internal reconnaissance of a
private build brief, and nothing on the front page points at it. Both added files were checked
against the export's forbidden-content patterns, and neither names the sealed family — which
`tests/synth/test_family_docs.py` already asserts for the first of them.

## Decision 7 — The trial export was run, and it found four things

`docs/voice.md` §8 requires a trial into a throwaway clone before any export, because the
destination is replaced and a deletion is as quiet as an addition. The trial was run against a fresh
clone of `elijahagumba/phos` at `f1959d6`. **No export to the live repository was made and nothing
was pushed.**
<!-- evidence-ack: f1959d6 — the public repository elijahagumba/phos's own HEAD at the time of the trial, which is a different repository from this lab and not an object in it -->

**It would publish 1,549 files: 118 new, 24 modified, and nothing deleted.** The ADR 0381 trap does
not fire — `.github/assets` is untouched, so the twelve live assets stay. The front page's diff is
the two opening paragraphs and the new section, and the sanitiser touched none of the files added
here.

**It would also publish the unmerged branch.** The export's candidate set is `git ls-files` in the
checkout it runs from, so running it here would put PARTS R1–R5 into the public repository before
they are on `main`, together with the main-line backlog unexported since `f1959d6` — 20 new records
in all, of which only 0433–0439 are this programme's, and 13 plain-English notes, of which only 186
is. That is a decision about what is published and when, so it is named here rather than taken.

**It found a dead link this record created.** `docs/sim/README.md` links to `recon.md` in its own
table, and Decision 6 deliberately withholds `recon.md`. A sanitize rule now drops that target and
keeps its text, exactly as the rules for the other lab-only documents do. This is precisely what a
trial is for, and it is recorded rather than quietly patched.

**It found a dead link nobody created on purpose.** ADR 0369 was withheld under the ADR 0342 policy
and added to `exclude` and `[forbidden].paths` **without** the matching sanitize rule ADR 0334
received, so five exported records linked to a file that is not in the export. The rule is added by
the same pattern. Dead links across the exported ADR corpus fall from **11 to 4**.

The remaining four are stale filenames inside Accepted records, and every target exists under its
current name:

| Citing record | Cites | Current filename |
|---|---|---|
| 0395 | `0267-the-public-test-job-runs-a-fresh-clone.md` | `0267-role-files-reach-the-public-tree.md` |
| 0397 | `0316-the-joint-command-vector-is-declared.md` | `0316-the-joint-command-is-declared-before-either-champion-is-scored.md` |
| 0398 | `0112-a-window-is-a-span-of-seconds.md` | `0112-consistency-windows-by-sample-period-and-one-batadal-score.md` |
| 0416 | `0143-the-gate-look-is-spent.md` | `0143-the-plant-map-fails-the-gate.md` |

Repointing a link inside an Accepted record, or acknowledging it in place, is a judgement about
immutability and is left rather than taken here.

## Decision 8 — The exported suite is red, and the cause is not this change

The front page tells a reader to run `uv run pytest -q` on a fresh clone. In the trial export it
gives **36 failed, 6,183 passed, 48 skipped, 45 deselected, 79 errors**.

**One root cause.** `tests/genesis/` and `tests/guards/test_parity.py` read `docs/rules/`, which is a
symlink into `.cursor/rules/` — a `[forbidden].paths` entry — and the editor hook files under
`.cursor/` and `.claude/`, which are forbidden for the same reason. None of it is in the export, so
those tests cannot run there. `tests/eval/test_slow_marker.py`'s two failures are a cascade: it
shells out to `pytest --collect-only` and asserts a clean exit, which `tests/genesis/test_tiercheck.py`
breaks by reading the rule file at collection time.

**It predates this change by three weeks.** These tests arrived with ADRs 0412–0417 and have never
been trial-exported. Nothing in R1–R5 or in this record touches them, and the lab suite is green at
**6,526 passed** either way.

**It is not fixed here, and the reason is that the fix is a decision.** Three options, none free:
exclude those trees, which lowers the published test count and removes the guard-parity evidence
from the public repository; export `docs/rules/` and the hook files, which publishes the agent rules
those paths are forbidden to protect; or mark them `lab_only`, which `tests/conftest.py` already
skips in the public repository, keeping them visible and green at the cost of ~95 tests not running
there. The third matches an existing pattern and is the recommendation, and it is still a change to
a published number and to what the front page's green badge means.

**So the stale test count stays stale, now for a measured reason.** The exported tree collects
**6,345** tests, not 4,943 — but quoting a count for a suite that does not pass would be worse than
quoting an old one, so neither figure is written to the front page until the exportability decision
above is taken.

## Consequences

**The lab surfaces move with it, as ADR 0044 requires of an advancement.** `README.md` gains the
generator in the lab's own register, with file paths and the defects the gate found.
`encyclopedia/10` gains the subsystem; `encyclopedia/01` gains the public register and the custody
definition; `encyclopedia/12` catalogues ADRs 0433–0439. `easy to reads/186` is the plain-English
note — 180 to 185 are taken on other branches, and `scripts/check_number_allocation.py` (ADR 0292) caught the collision before it was committed — and its index records that notes 119 to 185 are
spread across branches and unlisted rather than pretending otherwise. The branch is unmerged, so ADR 0044 would have exempted all of this; it is done anyway,
because the request was about the public surfaces.

**What a hostile reader can now check that they could not before.** That the project states its own
evaluation defect on the front page. That the fix is described with its refusal rate rather than its
best case. That the sealed family's source is admitted to be present. That the sentence "nothing has
been scored on a generated plant" sits in the section that would most benefit from omitting it.

**One number on the front page is left stale, and Decision 8 now says why with a measurement.** The badge line and
the `Run it` section both say **4,943 tests**, with "about three minutes". PARTS R1–R5 added roughly
four hundred tests under `tests/synth/`, which `tests/*` exports wholesale, so both figures are
wrong — and the right ones belong to the **exported** tree, not the lab's 6,526. Computing them
means applying the manifest's include and exclude rules, which is what an export does. So they are
flagged here for the next export to recompute and are not edited now. ADR 0044 says keep the public
summary true and never invent a number; an unmeasured replacement would break the second clause to
satisfy the first.

**What this record does not do.** No measurement, no score, no detector, no corpus opened, no
harness run. No frozen number is requoted or moved: the HAI figures, the baseline figures, CERT 6B,
the command-lead freeze and v1's **8 of 12** are all untouched, and no claim of 10×, 2–3 pages a day
or ≥70% appears anywhere added here. The law paragraph is not edited. `.phos_roadmap_state.json` is
not touched, so `current_session` stays **P1**, the blocked human conversation, with Intelligence,
the API and the UI behind it. The design freeze is not reopened: ADR 0200's house style is unchanged
and no asset was drawn. **The trial export was run; no export to the live repository was.** Decisions 7 and 8 are its
findings. Publishing is a separate act and is not taken here.
