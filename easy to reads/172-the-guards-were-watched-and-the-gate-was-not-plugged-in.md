# 172 — The guards were watched, and the second editor was not listening

Decision record: ADR 0417. Date: 3 November 2026.

Two records in a row ended with the same sentence: *this has not been watched happening in the
other editor.* The scripts had been run one at a time, handed the shape of message that editor
sends, and every answer matched. That proves the two scripts agree. It does not prove anything is
connected.

So this session went looking for the connection, and found two different things.

## The five warnings do fire

Inside a real Cursor session, a command naming a sealed corpus drew this, unprompted:

```
PHOS guard: a tool call naming red-tier data
  rule: docs/rules/data-tiers.md — never read, score or iterate on the validation corpora
  `hai-23.05` is red tier
  `hai` is red tier
  ADR 0117's gate look 1 is spent (ADR 0143); a new look needs Elijah to authorise it
  tool: Read
  advisory: this call was not blocked. Read the rule before going further.
```

That is the guard doing exactly what it was built to do: speak before a protected corpus is
opened, and then let the read go through rather than becoming a wall. Cursor accepted the reply —
its own log calls it `executed successfully and returned valid response`. Forty-six warnings were
delivered this way and none of them blocked anything. Reading a sealed path, writing the frozen
result log, committing an advancement without its public record: all warned, all allowed.

## The gate was not connected at all

The editor keeps a log of which hook files it loads, and it says this on every start:

```
Project config path (phos): <workspace>/.cursor/hooks.json
ERROR: Failed to parse project hooks configuration
No project hooks configuration found
Loaded Claude project hooks
```

That file is not there. The work was on a side copy of the repository, and the editor reads its
hook wiring from the **root** of the workspace — the main copy — where the file does not exist
because this work has not been merged yet. So the two hooks that refuse were never loaded. Counting
every event the editor has ever raised: fourteen thousand on the general tool event, thirty-eight
on workspace open, and **zero** on either of the two events the gate is registered for. Zero on
"before a shell command" and zero on "before a file is read".

The gate is the one check in this repository that stops rather than warns. On this checkout it
stopped nothing.

## One thing was deliberately not done

The plan was to watch the gate refuse a harmless-looking command. It turned out not to be harmless:
`scripts/measure_baseline_table.py` has no option parsing at all, so `--help` is ignored and the
whole recompute runs — and that recompute reads four corpora the tier rule lists under **never
read**. All four are sitting in `data/`. Watching the gate refuse would have meant opening them.
The command was not run; the gate script was handed the message the editor would have sent instead,
which is the weaker evidence, and this record says so rather than dressing it up.

## A real defect, found by using the thing

Writing the first question into the research store created a lock file beside the records. That
file is deliberately not committed, and it exists only on a machine where the tooling has run. But
the evidence audit had been told, in the record that introduced the lock, that the lock is absent —
and an audit that resolves paths against the disk cannot tell "absent because it is not evidence"
from "absent because it has not run yet". So the audit failed, which means **CI failed**, on a
change that was correct.

The fix is one idea: a file the tooling creates while it runs is not a citation, and whether it is
present says nothing about a record. The lock and the half-written temporary files are now retired
before anything tries to resolve them, and an explanation referring to one is no longer reported as
stale. Verified by running the audit twice, once with the lock present and once with it removed:
identical output, both passing. No accepted decision record was edited to get there, because the
record was right and the checker was not.

## What is still not known

Whether the gate would refuse correctly in a live session — it was never loaded. Whether the two
shell and file-read events work in Cursor at all — they never fired. Whether a warning that is
delivered changes what happens next — the only evidence is that the work continued, which is also
what happens when a warning is ignored.
