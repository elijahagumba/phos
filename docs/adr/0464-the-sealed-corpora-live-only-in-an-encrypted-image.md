# ADR 0464 — The sealed corpora live only in an encrypted image

- **Status:** Accepted
- **Date:** 2026-11-23
- **PART:** Method. Records where the sealed files live. No scoring.
- **Supersedes:** nothing
- **Depends on:** [ADR 0460](0460-the-atlas-research-method-runs-in-five-roles-and-scores-one-unseen-number.md),
  [ADR 0461](0461-the-17-november-sweep-is-recorded-and-the-tainted-detectors-refuse.md)

## Context

ADR 0461 said a hash manifest of the sealed files was the right next step, and that it was not done there. Accepted records stay as written, so this is a new record rather than a note added to that one.

The owner hashed the five never-read corpora and the two sealed held-back halves before moving them. The list is `docs/method/red-sealed-manifest.txt`: 62 SHA-256 lines. Six are `hai`, seven are `hai-21.03`, 21 are `hai-22.04`, 11 are `hai-23.05`, five are `batadal`, nine are `daypsci-v1-heldout`, and three are `fdia-synthetic-microgrid-heldout`. This record does not recompute those hashes. No file under `data/` was opened to write it.

The owner then moved the files into an encrypted disk image outside `~/dev`. They are mounted only for a declared referee score.

This checkout no longer has those seven folders. Six files in them were tracked, which is all git held for those folders: `data/hai/manifest.json`, `data/hai/topology.toml`, `data/hai-21.03/roles.toml`, `data/hai-22.04/roles.toml`, `data/hai-23.05/roles.toml`, and `data/batadal/manifest.json`. This change removes them from the tree. The payloads were never committed.

A count of names, with no file opened, found one worktree that still holds a full copy. `phos-g-dnp3` has the same seven folders, with the same file counts as the manifest. Other worktrees under `~/dev` still have only those six tracked files, because the commits they are on still contain them. This record does not delete the copy in `phos-g-dnp3`.

## Decisions

1. **The manifest is the byte list.** `docs/method/red-sealed-manifest.txt` is the owner's hash of those 62 files, taken before the move. A later check compares the image to this list. It does not open a checkout to do it.

2. **The seven folders live only in the encrypted image.** They are mounted only for a declared referee score, and unmounted after. They are not part of a checkout of this commit. The six tracked files leave the tree here.

3. **The resolver and the guard test still apply.** ADR 0461's refusal stands. Absence from the checkout does not replace it. Neither held-back half and no red corpus is treated as unseen. 87 of 120 does not move. v1 stays 8 of 12.

4. **A test that reads one of the removed role files skips when the file is absent.** If the file is present, the test runs. The plant-map pin still reads its bytes from the commit ADR 0142 names, through `git show`, not from the working tree.

## What this record does not do

- It does not edit ADR 0461.
- It does not delete the copy in the `phos-g-dnp3` worktree.
- It does not identify the program that read the files on 17 November.
- It does not run that mechanism check, and it does not generate a fresh held-out batch.
- It does not score anything, and it does not append `eval_runs/log.jsonl`.

## Consequences

A clone of this commit does not contain the seven folders. A referee who needs them mounts the image for that score only. The six entry points still refuse before they open a path.

The copy in `phos-g-dnp3` is still on disk. Until it is removed, "absent from every checkout" is the rule and not yet the fact on this machine.

## What would reverse this

Putting any of those files back into a checkout, or treating one as unseen, needs its own record and Elijah. Removing the leftover copy in `phos-g-dnp3` does not need a new record. It is the rest of this one.
