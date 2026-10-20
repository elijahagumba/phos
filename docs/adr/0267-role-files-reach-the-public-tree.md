# ADR 0267 — Role files reach the public tree, and absent pins skip

- **Status:** Accepted
- **Date:** 2026-10-20
- **PART:** public repository CI
- **Depends on:** [ADR 0118](0118-decisions-and-outcomes-in-a-chained-ledger.md),
  [ADR 0123](0123-the-plant-map-proposed.md)

## Context

`elijahagumba/phos` has failed its test job on every run for days. GitHub run
39399903146, on the public revision 164791b, fails "Tests" with 26 failures. The
run before the last export failed with the same 26, so the export did not cause them.

21 of the 26 read a `roles.toml`. The lab gitignore un-ignores those files because
they are hand-authored declarations, and `docs/rules/data-tiers.md` says data files
are never committed, role files excepted. `public/overlay/.gitignore` ignored
`data/*/*` and un-ignored only `manifest.json`, `topology.toml` and
`sentiel-manifest.json`. `scripts/export_public.py` wrote the five role files into
the public tree, and `git add` then skipped every one. `git check-ignore -v` on
`data/hai-20.07/roles.toml` in the public checkout reported `.gitignore:24`.

4 of the 26 read under `experiments/`. That tree is not an include pattern in
`public/manifest.toml`. Exporting those small text files is the alternative; this
record does not take it. The pins are the ones ADRs 0103 and 0104 rest on.

1 of the 26 pins the sha256 of the first 185 lines of `eval_runs/log.jsonl`. The
lab prefix is `ca7c597e4519bc2b9f19142e8d637f67be8c8774f0b0b18ed241a11e56f80461`.
The exported prefix is `db5ae1aa2cf83666e68ae7b352c778618cb57a3a351690a0407cbcf753707de5`.
The manifest sanitiser strips the author's absolute checkout path, so the same lines
are different bytes. Eighteen lines in the prefix change. Line 41 is one of them.

## Decision

1. **`public/overlay/.gitignore` un-ignores `data/*/roles.toml`.** The comment says
   why: a role file is a declaration of sensors, actuators and setpoints, not a
   dataset. Payloads stay ignored. The 21 tests run where the files are present.
   They do not skip.
2. **An absent experiment pin skips, and says why.** The four tests are
   `test_the_checks_are_on_disk`, `test_the_candidate_bytes_are_the_frozen_file`,
   `test_the_candidate_is_attempt_6_unchanged` and
   `test_a_declaration_is_never_overwritten`. The skip fires only when the path is
   not a file. A checkout that has the file still fails if the bytes move.
   Exporting the files remains open and is not done here.
3. **The log prefix carries both digests, each named.** Lab bytes, the prefix that
   still contains an absolute checkout path, must match the lab digest. Exported
   bytes, the prefix after the sanitiser, must match the exported digest. Any other
   digest fails. No other assertion is loosened.

## Consequences

The public test job can pass once this tree is exported and the role files are
committed there. This record does not commit or push `~/dev/phos-public`. Publishing
stays Elijah's call. The lab suite still runs the four pins and still refuses a
moved byte.

## What would reverse this

Ignoring role files again, skipping a pin whose file is present, accepting a third
digest, or treating an exported experiment file as optional inside the lab.
