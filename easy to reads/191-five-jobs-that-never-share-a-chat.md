# 191. Five jobs that never share a chat

*Atlas research used to be done by one assistant that had the idea, built it, chose the data to
test it on, and judged the result. From now on those are separate jobs, done in separate
conversations that never swap, and progress is measured by one number on data nobody has seen.*

## Why split the work

When the same mind builds a thing and then judges it, it judges what it expected to build. This
project already has the proof. One piece of work went through five rounds of attack by a red team,
and four of those rounds found a real defect in a version a judge had already passed. Every defect
was found by someone whose job was to break the work, not to confirm the last fix.

So the method makes that the rule rather than the exception.

## The five jobs

**The scout** reads published research on detecting attacks on industrial plants, reads the
project's own record, and finds where Atlas is weakest. It proposes ideas, each with a pass mark
written down before anything is built, and with the result that would show the idea wrong. It
changes no code.

**The builders**, up to three a week, each try one idea in their own copy of the code. They work
only on practice data. They cannot see the sealed data the idea will be judged on, and they are not
allowed to ask for it. They do not get to say whether they won.

**The breaker** comes in after the builders stop. Its job is to make each claimed win fail, using
only the physics of the plant and the plant's own published description. It is never allowed to
look at the engine's code, so it attacks the way an outsider would.

**The referee** starts fresh, reads only what the others committed, opens the sealed data, and
scores each idea exactly once through the machinery the project already uses to refuse a second
look. It writes the verdict and updates the scoreboard. It cannot edit the code.

**Elijah** is the fifth job and the only person. He chooses the direction, deals with partners,
and does anything that needs a human: a password, a signature, a real plant.

## One number

The number is called **unseen catch**: how many attacks Atlas puts in front of the operator, within
the limit of eight alerts a shift, on a batch of simulated plant runs that nobody has looked at. It
starts at **87 of 120**, with **6 of 40** harmless events drawing an alert by mistake. Those figures
are copied from the one time Atlas was scored on runs nobody had seen, not worked out again.

An idea only counts if it catches more than 87, does not raise more than 6 false alarms, and does
not lose a single kind of attack it used to catch. A gain bought with extra false alarms is not a
gain.

## Checking that unseen means unseen

The proposed batch is a set of twenty simulated runs that was planned weeks ago and never made. That
was checked on disk, in every copy of the project on this machine, and in its whole history.

The same check found something else. Two other held-back sets, which a record said in early November
had never been opened, show on disk that their text files were read in one four-minute burst on 17
November. So were files in every other dataset folder, including ones the project is never allowed
to read. Nothing in the record says what did it. Nothing shows the contents were used, and nothing
shows they were not. Until that is explained, neither set is called unseen.

## What the first scout found

The three weakest places, all from that one unseen test:

- **Frozen readings: 3 of 20 caught.** An attacker holds a level reading still while the tank keeps
  moving.
- **Maintenance look-alikes: 5 of 20 caught.** An attacker shuts a valve exactly the way a
  maintenance job does.
- **False alarms: 6 of 40.** Four on genuine maintenance, two on ordinary setpoint changes.

The best idea is a law of physics the project has already written down: when the tank is draining
with nothing coming in, the level has to fall at the rate the plant states. A frozen reading cannot
fall, so it breaks the law. Next is checking that every valve forced shut has a work order behind
it, though on this simulator that test passes almost by design. Third is reading a real controller
program, written in the standard industrial language, and checking the plant still obeys it.

Several ideas were set aside because the record already shows them wrong, and the pass says which
and why, so nobody tries them again.

The most useful finding is uncomfortable: **every idea that is still alive needs a decision from
Elijah before anyone may build it.** The physics law waits behind a rule that keeps that rung closed
until January. The work-order check is a new law outside any open programme. The controller program
belongs to a different simulated plant than the one the current rules cover. None of those can be
waved through by an assistant.

## What did not happen

Nothing was scored. No sealed data was opened. No code was changed. The scoreboard of the first
version still reads eight of twelve. After four weeks, Elijah reviews whether the method earned its
keep, and keeps it, changes it, or stops it.
