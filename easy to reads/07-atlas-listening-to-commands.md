# Atlas: listening to commands

**What this is:** the packet adapter — reading the control network itself, not only the historian’s
sensor table.

**Why it exists:** process values cannot tell an operator’s legitimate valve move from an
attacker’s. Both can look like “the plant changed.” **Who commanded whom** can.

## Watching who is allowed to turn which valves

Think of a locked plant: sensors are the gauges on the wall; **commands** are the keys and the
hands on the switches.

Atlas peels network packets carefully. Hostile or malformed input is contained at a single
dissection seam (the library is not trusted throughout the program). From healthy traffic it
learns:

- how a **device** usually commands (what it *is*, behaviourally)
- the **command graph**: who talks to whom

A new edge on that graph — a workstation that never commanded this PLC, and now does — is a
**relationship change**. That is the first kind of evidence Atlas ever had that can support
“unauthorised control” and contradict “ordinary process upset.” A real process disturbance moves
readings. It does not, by itself, hire a new commander.

Honest limit, kept: a **commissioning engineer** and an **intruder** can leave behind the same
**new function on a station that already commanded this PLC**. Command evidence still cannot tell
those two apart.

The limit that **moved**: a **device that has never commanded this target**, and now writes, is
not how plant engineers work. That marked “unknown master” now **contradicts** maintenance and
**supports** unauthorised control. That split is wired. On the writes we designed it **moved**
the attack explanation up in all four windows and made it the **unique** leader in **one** —
a diagnostic that a silence flood was drowning the story, not ≥70% and not a field rate.
When attack and maintenance saturate at the same ceiling, PHOS **refuses** a unique winner
rather than letting alphabetical order name maintenance. Silence is judged against a
**comparable stretch** of the learned graph; a finding enters a window’s story only if it
**shares a device** with that window’s command act. See
[quieter queues](13-quieter-queues-and-honest-ranking.md),
[silence, clocks, and who belongs in the story](15-silence-stretch-and-who-belongs-in-the-story.md),
and [ADR 0036](../docs/adr/0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md).

## The measurement that was refused

The pipeline is complete: command facts become the same `Evidence` objects sensor deviations do,
and they enter the reasoning engine. A **real-world detection rate** from this path was
**not published**, because PHOS did not have a labelled public packet corpus it was willing to
score. Running a self-test on a hand-built capture proves the plumbing, not the plant.

Later, on the **synthetic** adversary, a “did command-reasoning move the ranking?” figure exists.
That figure is an **ordinal rank** on attacks **we wrote**, against a plant **we wrote**, judged by
templates **we wrote**. It is **not** a detection rate and must not be quoted as one. The report
prints that warning beside the counts, not only in a footnote.

## What this is not

- Not a permission to feed a parsed packet *table* and skip the dissector. The security argument
  is built around containing raw frames.
- Not the ≥70% “top-ranked explanation in attack windows” sprint target. After ADR 0027 the
  breaking harness posted **led in 0 of 16** known-station writes (issuers `scada` / `hmi`).
  Unknown-master writes from a silent engineering workstation **moved up in 4 of 4** and
  **uniquely led in 1 of 4** — a D2 diagnostic with the standing rank caveat, not a field rate
  ([ADR 0034](../docs/adr/0034-command-lead-rate-zero-on-known-link-writes.md),
  [ADR 0035](../docs/adr/0035-unknown-master-writes-still-do-not-lead.md),
  [ADR 0037](../docs/adr/0037-silence-is-judged-against-a-comparable-learned-stretch.md),
  [ADR 0038](../docs/adr/0038-a-windows-story-attaches-graph-findings-by-entity-reachability.md)).
  After ADR 0036 a ceiling tie is a **refusal**, not maintenance uniquely leading by alphabet.
  Do not pool the two issuer kinds.

## Where to read more

- Decisions: [ADR 0012](../docs/adr/0012-dpkt-the-dissector-seam-and-containing-hostile-packet-input.md),
  [ADR 0013](../docs/adr/0013-command-behaviour-features-device-identity-and-the-command-graph.md),
  [ADR 0014](../docs/adr/0014-command-evidence-the-second-boundary-door-and-the-unrun-measurement.md),
  [ADR 0027](../docs/adr/0027-unknown-master-writes-are-not-maintenance.md),
  [ADR 0034](../docs/adr/0034-command-lead-rate-zero-on-known-link-writes.md),
  [ADR 0035](../docs/adr/0035-unknown-master-writes-still-do-not-lead.md),
  [ADR 0036](../docs/adr/0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md),
  [ADR 0037](../docs/adr/0037-silence-is-judged-against-a-comparable-learned-stretch.md),
  [ADR 0038](../docs/adr/0038-a-windows-story-attaches-graph-findings-by-entity-reachability.md)
- Code: `src/phos/atlas/` command modules; `scripts/evaluate_command_detection.py`
