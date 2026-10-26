# ADR 0328 — Manual is one school, and the page does not choose

- **Status:** Accepted
- **Date:** 2026-10-24
- **PART:** Atlas, the controller comparison
- **Supersedes:** nothing
- **Depends on:** [ADR 0321](0321-the-controller-comparison-is-true-or-false.md)

## Context

On 24 October 2026 a public conversation among people who program
controllers answered one question about `controller_valve`. The question
was whether a tank above its maximum, with the valve still open, should
alarm after an operator had switched that valve to manual.

The answers were not a plant export, not a labelled corpus, and not a
score. They were a map.

- If the valve should never be open above the maximum, some would force it
  shut instead of alarming. Whether that condition alarms at all is for
  process engineering to decide. There is no single answer.
- One school still forbids, in manual, whatever could break the machine.
- One school treats manual as privileged, and steps the automatic check
  aside.
- One school decides, for that process, which limits remain.
- A message can stay on the screen during manual without stopping every
  part of the machine.
- Operator manual and maintenance manual are different. Maintenance is the
  trusted one. A protection left on during manual, because people confuse
  the two, can lock the machine so it cannot move.
- Hiding a valve behind an operator login fails once the password is
  shared.

ADR 0321 already chose the second school for this law. A mode that is not
the release value 3 means the automatic comparison was not in force.
Manual is unstated. Silence is not a break. The page does not move a
valve. This conversation does not replace that decision. It says the
decision is one situation, not a rule for every plant.

No code was edited. No corpus was generated or scored.
`eval_runs/log.jsonl` was not appended. Held-out data was not opened.
v1 stays 8 of 12. This page is not a field result. P1 stays blocked.

## Decision

**Manual on `controller_valve` stays unstated. The page does not choose
among the other schools, and it does not grow a new law from this
conversation.**

The check is unchanged. Both modes at 3, and a valve that is not the
value the quoted comparison writes, is one break per side. Any other mode
is manual, and that law is unstated. There is one manual. It is not split
into operator and maintenance. The page does not see a login. The page
does not force a valve shut, and it keeps no protection that can lock a
machine. A message that remains during manual would be a different law. No
plant has written that law here. No predicate is added.

### Options

1. Alarm in manual, so a message stays up. The same conversation said
   there is no single answer. Refused.
2. Force the valve shut above the maximum. The page does not command the
   plant. Refused.
3. Split operator manual from maintenance manual, or read a login. No
   plant named that split, and a password is not an inlet this page has.
   Refused.
4. Leave ADR 0321 in force and write the map down. Chosen. No number
   moves.

## Consequences

**Gained.** A later session cannot treat this conversation as a tuning
note. The quiet manual case is school two of three. The page still does
not force, does not distinguish who is allowed to hold the valve, and
does not deadlock a machine.

**Cost.** The page still takes the message off in manual. One speaker
wanted that message to remain, without stopping the machine. This record
does not build that message. v1 stays 8 of 12. P1 stays a human
conversation.

## What would reverse this

A plant exports its files and writes, in its own words, a law that keeps a
message during manual, or that separates operator manual from maintenance
manual. That law is declared before any predicate. A chat that names the
schools is not that writing.
