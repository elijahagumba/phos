# 197 — A controller export, and the one rule it gave up

**No number on this page is a detection result.** Nothing here was scored against an attack, a
fault or a label. This is about a reader that turns a controller program into draft rules, and
about how little it got from the only programs it was allowed to try.

Atlas checks the rules your plant names. Writing that register by hand is the part an engineer has
to do before anything else happens, so the obvious question is whether the controller already
knows. A Rockwell PLC is programmed through Studio 5000, and a Studio 5000 project exports as an
L5X file: XML, with the ladder logic in it as text. If the interlocks are in there, they could be
read out instead of typed in.

## What it reads

`phos.atlas.l5x` looks for one shape, and only one: a rung where a comparison of a tag against a
number drives an output. "If the level is above 8.5, energise the alarm" is that shape. It becomes
a draft rule with the tag, the operator, the number and the output named.

Everything else is listed rather than guessed. A rung using an instruction the reader does not
model is named with its line and the reason. A rung with two comparisons at once is refused rather
than split. A `CMP` instruction carries its comparison as a free-text expression, and the reader
accepts only the plain `tag operator number` form of it, refusing anything more involved such as a
modulus or a boolean. A routine that is not ladder at all, which in Rockwell means structured
text, function block or sequential function chart, is named separately rather than counted as a
failure, because "this reader read 18 of 25 routines" is a fact a reviewer needs and "it failed 7
times" is not the same statement.

It also will not follow a `JSR` jump into another routine. The jump is listed as unmodelled.

## What it did on four public exports

Three public projects, all permissively licensed, were fetched and read. `hutcheb/acd` is
Apache-2.0, `tnunnink/L5Sharp` is MIT, and `JeremyMedders/LogixLibraries` is MIT, which supplied
two of the four files. Each licence was checked by reading the licence text itself rather than a
badge. Nothing was committed to this repository; the files were fetched to a temporary directory,
read, and left out of the test suite, because a test that needs a network fetch reports a broken
build when the network is what broke.

| Export | Draft rules | Ladder rungs not readable | Routines not ladder |
|---|---|---|---|
| `ACDTestsWithAOI.L5X` | 0 | 4 | 3 |
| `Test.L5X` | 1 | 18 | 2 |
| `Dev_PackML_State_Program.L5X` | 0 | 614 | 7 |
| `Numeric_Program.L5X` | 0 | 15 | 21 |

One rule, out of four real controller exports. It was `GT(SimpleInt,100)` driving an output: a tag
compared against a number, which is the one shape the reader models, appearing once.

## Why the count is so low, and why that is not the reader's fault

**They are libraries, not plants.** PackML is a state machine framework; its ladder routines are
hundreds of contacts wired to jumps into structured text. `ACDTestsWithAOI` exists to exercise an
add-on instruction. `Numeric_Program` is a numeric instruction library. None of them is a tank, a
pump station or a line, so none of them holds the process interlocks and alarm thresholds this
reader is looking for. A library has few thresholds because it is not guarding a process.

**Comparisons are rarer in real ladder than you would expect**, and when they appear they are
often written as `CMP`, whose expression the reader will read only in its plain form. The cost of
that deliberate narrowness is visible here.

**Most routines are not ladder.** A large share of the routines across these files are structured
text, function block or sequential function chart. The reader names them and stops. Reporting them
as untouched rather than folding them into a failure count is the difference between a register
that honestly covers part of a program and one that claims to cover all of it.

## The comparison that could not be made

The next question is how many derived rules agree with hand-written ones. `phos.atlas.l5x_agreement`
compares the reader's output against the six setpoints in the ICSSim development corpus, which were
read out of the simulator's source by hand.

The answer is **0 of 6**, on both exports it could be run against, and that zero is correct rather
than a defect. The hand-written record describes ICSSim: a tank, a conveyor, their tag names. The
exports are a test project and a state machine framework. They share no tag names and no process.
A match was never available, and a number claiming one would have been manufactured.

So the comparison as it stands cannot answer the question. What it can do is decline to pretend:
the matched, missed and unknown counts are reported separately and never combined into a score.

## What would actually settle it

An L5X export of a program whose rules were also written down by hand, independently, before the
export was read. No public sample under a permissive licence is a water or pumping control program
with a published rule list, so that file does not exist to be downloaded. It needs a plant that is
willing to share an export, or a program written for the purpose and declared before it is read.

## What this does and does not show

It shows that the reader runs on real Rockwell exports without crashing, that it finds the one
instruction shape it models, and that it names everything else with a reason.

It does not show that a register can be generated instead of written. On the evidence here it
cannot. The reader is a starting point for an engineer with a real program in front of them, and
the rules Atlas checks are still the ones you name.
