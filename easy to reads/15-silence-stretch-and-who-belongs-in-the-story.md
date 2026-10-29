# Silence, clocks, and who belongs in the story

**What this is:** two mechanical honesty fixes after “who commanded whom” was already on the
chart. A quiet learned link is judged against a **comparable stretch** of normal, not against a
five-day smear. A finding enters a window’s **story** only if it shares a device with that
window’s command act — or *is* the unknown-master write.

**Why it exists:** after a tie stopped being an alphabetical winner
([competing explanations](05-competing-explanations.md)), two remaining bookkeeping errors could
still make maintenance look well-supported for a rogue write. Neither was a plant event.

## A quiet minute is not a five-day smear

Imagine a poller that wrote twelve times in five days of training. If you turn that into a
**rate** and ask a **one-minute** live window “were you silent?”, every quiet minute of every
learned link looks like an act. That is a duration mismatch, not a valve going dark.

Atlas now asks a narrower question: in a **comparable stretch** of the learned graph, did this
link typically carry a command? A chatty SCADA poller that talks every minute is still reported
every live window it misses. A burst smeared across a long train is not. Learned span versus live
span is written on the finding, so the mismatch is reconstructable.

That cut the synthetic unknown-master live capture from roughly **1,450** graph findings to
**13**. It is not a licence to raise “how many commands before we bother” until the attack
uniquely leads
([ADR 0037](../docs/adr/0037-silence-is-judged-against-a-comparable-learned-stretch.md)).

## Sharing a clock is not sharing a command

Those remaining findings could still **all** enter one story because they happened in the same
correlation window. Every silent poller then supported “engineering maintenance” for a rogue
write it had **no path to**. The arrows on the narrative were evidence→hypothesis
co-occurrence, not plant causality.

The rule now: a graph finding may attach to a window’s story only if it **shares an entity**
with in-window command activity (an unknown master, or a new function on a learned link), or
**is** the unknown-master finding itself. A silent HMI talking to a different PLC does not argue
for maintenance on an engineering write to this one. A chatty SCADA that *is* the issuer (or
shares the commanded device) still can — power-plant silence is real, not a smear.

Analogy: a ward going quiet overnight is not evidence about a surgery in another building unless
they share a patient or a surgeon. The identities come from the command graph Atlas already
learned. They are **not** clustered from co-movement
([ADR 0038](../docs/adr/0038-a-windows-story-attaches-graph-findings-by-entity-reachability.md)).

`ground_event` is still the three-way table an operator can ask without reading hypothesis order:
**unauthorised**, **commanded**, or **uncommanded**. It is not a probability.

## Last harness rows (attacks we wrote)

Issuer kinds stay **apart**. `leads` means unique `unauthorised_control_activity`, never
“insufficient evidence” sorted first, never a non-empty tie listing at rank 1.

| Issuer kind | Moved up | Unique lead | n |
| --- | ---: | ---: | ---: |
| Known-station (`scada` / `hmi`) | 6 | **0** | 16 |
| Unknown-master (silent `engineering`) | 4 | **1** | 4 |

The **1 of 4** is only `wt-unknown-master-near-invisible`. The subtle window still lists at
rank 1 with two unauthorised-control hypotheses tied, so it is **not** a unique lead
([ADR 0036](../docs/adr/0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md)). That 1/4
is a **diagnostic** that the silence flood was a real mechanism. It is not ≥70%, not a field
rate, and not a reason to keep cutting silence or tightening reachability until 4/4.

The unknown-master corpus still posts **1.1650 false positives per normal hour**. Do not quote
its recall as detection.

## What this is not

- Not the ≥70% command-ranking contract. Completing these sessions does not earn it.
- Not a claim that PHOS now knows plant physics. Sharing an entity is the smallest declared
  relation already on the finding.
- Not a retune of templates, priors, or “how quiet before we emit silence.”
- Not a public labelled command capture. That measurement is still refused or waiting
  ([listening to commands](07-atlas-listening-to-commands.md)).

## Where to read more

- [ADR 0036](../docs/adr/0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md),
  [ADR 0037](../docs/adr/0037-silence-is-judged-against-a-comparable-learned-stretch.md),
  [ADR 0038](../docs/adr/0038-a-windows-story-attaches-graph-findings-by-entity-reachability.md)
- Code: `src/phos/atlas/packet/graph.py`, `src/phos/atlas/command_grounding.py`,
  `src/phos/reasoning/engine.py`
- Primary attachment test:
  `tests/atlas/test_command_evidence.py::test_a_silent_unrelated_poller_does_not_support_maintenance_for_a_rogue_write`
